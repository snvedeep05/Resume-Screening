const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

const headers = () => ({
  "x-api-key": API_KEY,
  "Content-Type": "application/json",
});

export async function fetchJobs() {
  const res = await fetch(`${API_URL}/jobs`, { headers: headers() });
  return res.json();
}

export async function fetchJob(jobId: number) {
  const res = await fetch(`${API_URL}/jobs/${jobId}`, { headers: headers() });
  return res.json();
}

export async function createJob(jobTitle: string, jobConfig: object) {
  const res = await fetch(`${API_URL}/jobs`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ job_title: jobTitle, job_config: jobConfig }),
  });
  return res.json();
}

export async function updateJob(jobId: number, data: { job_title?: string; job_config?: object }) {
  const res = await fetch(`${API_URL}/jobs/${jobId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function generateJobConfig(jobDescription: string) {
  const res = await fetch(`${API_URL}/jobs/ai-generate`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ job_description: jobDescription }),
  });
  return res.json();
}

export async function startScreening(jobId: number, batchSize: number, zipFile: File) {
  const form = new FormData();
  form.append("job_id", String(jobId));
  form.append("batch_size", String(batchSize));
  form.append("zip_file", zipFile);
  const res = await fetch(`${API_URL}/screening/start`, {
    method: "POST",
    headers: { "x-api-key": API_KEY },
    body: form,
  });
  return res.json();
}

export async function uploadSingleResume(jobId: number, file: File) {
  const form = new FormData();
  form.append("job_id", String(jobId));
  form.append("resume_file", file);
  const res = await fetch(`${API_URL}/screening/upload-single`, {
    method: "POST",
    headers: { "x-api-key": API_KEY },
    body: form,
  });
  return res.json();
}

export async function getRunStatus(runId: number) {
  const res = await fetch(`${API_URL}/screening/runs/${runId}`, { headers: headers() });
  return res.json();
}

export async function fetchResults(
  jobId: number,
  params?: { search?: string; decision?: string; min_score?: number; max_score?: number; limit?: number; offset?: number }
) {
  const query = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") query.set(k, String(v));
    });
  }
  const res = await fetch(`${API_URL}/screening/results/job/${jobId}?${query}`, { headers: headers() });
  return res.json();
}

export async function bulkUpdateDecision(resultIds: number[], decision: string, reason?: string) {
  const res = await fetch(`${API_URL}/screening/results/bulk`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ result_ids: resultIds, decision, reason }),
  });
  return res.json();
}

export async function updateDecision(resultId: number, decision: string, reason?: string) {
  const res = await fetch(`${API_URL}/screening/results/${resultId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ decision, reason }),
  });
  return res.json();
}

export async function getDecisionHistory(resultId: number) {
  const res = await fetch(`${API_URL}/screening/results/${resultId}/history`, { headers: headers() });
  return res.json();
}

export function getExportUrl(jobId: number, decision?: string, minScore?: number) {
  const params = new URLSearchParams();
  if (decision) params.set("decision", decision);
  if (minScore !== undefined) params.set("min_score", String(minScore));
  return `${API_URL}/screening/results/job/${jobId}/export?${params}`;
}
