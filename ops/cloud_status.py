"""Read-only RaOne-Bot pre-deployment inventory. Run with Python 3 in Cloud Shell."""
import datetime
import json
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT = "ravanatek"
NUMBER = "939944415589"
SITE = "raonebot"
DATABASE = "raone-bot-db"
HOSTING = "https://firebasehosting.googleapis.com/v1beta1"
errors = []


def gcloud(*args):
    return subprocess.check_output(["gcloud", *args], text=True).strip()


def read_api(url):
    try:
        request = Request(url, headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as exc:
        errors.append({"url": url, "error": str(exc)})
        return {}


def list_all(url, field):
    items = []
    suffix = ""
    while True:
        page = read_api(url + suffix)
        items.extend(page.get(field, []))
        cursor = page.get("nextPageToken")
        if not cursor:
            return items
        suffix = "?" + urlencode({"pageToken": cursor})


def public_status(url):
    try:
        with urlopen(url, timeout=20) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except (URLError, TimeoutError) as exc:
        errors.append({"url": url, "error": str(exc)})
        return None


def main():
    global token
    if gcloud("projects", "describe", PROJECT, "--format=value(projectNumber)") != NUMBER:
        sys.exit("Project number mismatch.")
    token = gcloud("auth", "print-access-token")
    root = f"{HOSTING}/projects/{NUMBER}/sites"
    sites = []
    for item in list_all(root, "sites"):
        name = item["name"].split("/")[-1]
        releases = read_api(f"{HOSTING}/sites/{name}/releases?pageSize=1")
        release = next(iter(releases.get("releases", [])), {})
        row = {"site": name, "url": item["defaultUrl"], "http": public_status(item["defaultUrl"]),
               "latest_release": release.get("name"), "version": release.get("version", {}).get("name"),
               "release_time": release.get("releaseTime")}
        if name == SITE:
            for endpoint, field in [("channels", "channels"), ("customDomains", "customDomains")]:
                row[field] = [entry["name"] for entry in list_all(f"{root}/{name}/{endpoint}", field)]
        sites.append(row)
    if SITE not in {row["site"] for row in sites}:
        errors.append({"site": SITE, "error": "Target missing from Hosting inventory"})
    data = read_api(f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases")
    if data.get("unreachable"):
        errors.append({"unreachable_database_locations": data["unreachable"]})
    databases = [{"id": db["name"].split("/")[-1], "location": db.get("locationId"),
                  "type": db.get("type")} for db in data.get("databases", [])]
    print(json.dumps({"time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "project": PROJECT, "project_number": NUMBER, "sites": sites,
                      "databases": databases, "target_database": DATABASE, "errors": errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
