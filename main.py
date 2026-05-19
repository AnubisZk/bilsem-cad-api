from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid, os, re, subprocess
from datetime import datetime

app = FastAPI(title="BİLSEM AI CAD Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS = {}
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BLOCKED = ["silah","weapon","gun","bomb","patlayici","bicak","kesici"]

def safety_check(prompt):
    return not any(w in prompt.lower() for w in BLOCKED)

def parse_dimensions(prompt):
    nums = re.findall(r'(\d+(?:\.\d+)?)', prompt)
    nums = [float(n) for n in nums if 1 <= float(n) <= 500]
    return {
        "width": nums[0] if len(nums) > 0 else 80,
        "depth": nums[1] if len(nums) > 1 else 40,
        "height": nums[2] if len(nums) > 2 else 8,
    }

def generate_with_claude(prompt, job_dir):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    code_prompt = f"""You are a build123d CAD expert. Write Python code using build123d to create the following part.
Rules:
- Only output Python code, no explanation, no markdown
- Save STEP to: {job_dir}/model.step
- Save STL to: {job_dir}/model.stl
- All dimensions in mm
- Minimum wall thickness 2mm
- Use export_step() and export_stl()
- Wrap in try/except and print errors

Part description: {prompt}
"""
    
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{{"role": "user", "content": code_prompt}}]
    )
    
    code = response.content[0].text
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        code = code.split("```")[1].split("```")[0]
    
    return code.strip()

def generate_fallback(prompt, job_dir):
    dims = parse_dimensions(prompt)
    w, d, h = dims["width"], dims["depth"], dims["height"]
    return f"""from build123d import *
with BuildPart() as part:
    Box({w}, {d}, {h})
    with Locations(({w/2-8}, {d/2-8}, {h/2}), (-{w/2-8}, {d/2-8}, {h/2}), ({w/2-8}, -{d/2-8}, {h/2}), (-{w/2-8}, -{d/2-8}, {h/2})):
        Hole(radius=1.5, depth={h})
    fillet(part.edges().filter_by(Axis.Z), radius=min(2, {h}/4))
export_step(part.part, "{job_dir}/model.step")
export_stl(part.part, "{job_dir}/model.stl")
print("done")
"""

def generate_cad(job_id, prompt):
    job_dir = f"{OUTPUT_DIR}/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    JOBS[job_id]["status"] = "generating"

    try:
        # Try Claude first, fallback to template
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                code = generate_with_claude(prompt, job_dir)
            except Exception as e:
                print(f"Claude error: {e}, using fallback")
                code = generate_fallback(prompt, job_dir)
        else:
            code = generate_fallback(prompt, job_dir)

        code_path = f"{job_dir}/model.py"
        with open(code_path, "w") as f:
            f.write(code)

        result = subprocess.run(
            ["python3", code_path],
            capture_output=True, text=True, timeout=90
        )

        if result.returncode == 0 and os.path.exists(f"{job_dir}/model.step"):
            dims = parse_dimensions(prompt)
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["files"] = {
                "step": f"{job_dir}/model.step",
                "stl": f"{job_dir}/model.stl" if os.path.exists(f"{job_dir}/model.stl") else None,
            }
            JOBS[job_id]["dimensions"] = dims
            JOBS[job_id]["completed_at"] = datetime.now().isoformat()
        else:
            # Fallback if Claude code failed
            code = generate_fallback(prompt, job_dir)
            with open(code_path, "w") as f:
                f.write(code)
            result2 = subprocess.run(["python3", code_path], capture_output=True, text=True, timeout=90)
            if result2.returncode == 0:
                dims = parse_dimensions(prompt)
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["files"] = {
                    "step": f"{job_dir}/model.step",
                    "stl": f"{job_dir}/model.stl" if os.path.exists(f"{job_dir}/model.stl") else None,
                }
                JOBS[job_id]["dimensions"] = dims
                JOBS[job_id]["completed_at"] = datetime.now().isoformat()
            else:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = result2.stderr[:500]

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)

@app.post("/generate")
async def generate(req: dict, bg: BackgroundTasks):
    prompt = req.get("prompt", "")
    student_id = req.get("student_id", "unknown")

    if not safety_check(prompt):
        raise HTTPException(400, "Prompt güvenlik filtresine takıldı.")
    if len(prompt) > 500:
        raise HTTPException(400, "Prompt 500 karakterden uzun olamaz.")

    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "job_id": job_id,
        "student_id": student_id,
        "prompt": prompt,
        "status": "queued",
        "created_at": datetime.now().isoformat()
    }
    bg.add_task(generate_cad, job_id, prompt)
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
async def status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job bulunamadı.")
    return JOBS[job_id]

@app.get("/download/{job_id}/{fmt}")
async def download(job_id: str, fmt: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job bulunamadı.")
    files = JOBS[job_id].get("files", {})
    path = files.get(fmt)
    if not path or not os.path.exists(path):
        raise HTTPException(404, f"{fmt} dosyası henüz hazır değil.")
    return FileResponse(path, filename=f"model_{job_id}.{fmt}")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "BİLSEM AI CAD Service", "claude": bool(os.environ.get("ANTHROPIC_API_KEY"))}
