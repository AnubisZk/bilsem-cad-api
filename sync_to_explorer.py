import requests, os, shutil

API = "https://bilsem-cad-api-production.up.railway.app"
EXPLORER_MODELS = os.path.expanduser("~/text-to-cad/skills/cad-explorer/scripts/explorer/dist/models")

def sync_job(job_id):
    # STL indir
    r = requests.get(f"{API}/download/{job_id}/stl")
    if r.status_code == 200:
        path = f"{EXPLORER_MODELS}/{job_id}.stl"
        with open(path, "wb") as f:
            f.write(r.content)
        print(f"✓ {job_id}.stl → Explorer models")
    
    # STEP indir
    r = requests.get(f"{API}/download/{job_id}/step")
    if r.status_code == 200:
        path = f"{EXPLORER_MODELS}/{job_id}.step"
        with open(path, "wb") as f:
            f.write(r.content)
        print(f"✓ {job_id}.step → Explorer models")

if __name__ == "__main__":
    import sys
    job_id = sys.argv[1] if len(sys.argv) > 1 else input("Job ID: ")
    sync_job(job_id)
