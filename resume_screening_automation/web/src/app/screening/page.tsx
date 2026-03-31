"use client";

import { useEffect, useState } from "react";
import { fetchJobs, startScreening, uploadSingleResume, getRunStatus } from "@/lib/api";

type Job = { job_id: number; job_title: string };

export default function ScreeningPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<number | "">("");
  const [batchSize, setBatchSize] = useState(5);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"zip" | "single">("zip");
  const [runId, setRunId] = useState<number | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchJobs().then(setJobs);
  }, []);

  useEffect(() => {
    if (!runId) return;
    const interval = setInterval(async () => {
      const s = await getRunStatus(runId);
      setStatus(s);
      if (s.status === "completed" || s.status === "crashed") {
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [runId]);

  const handleSubmit = async () => {
    if (!jobId || !file) return;
    setUploading(true);
    try {
      let result;
      if (mode === "zip") {
        result = await startScreening(Number(jobId), batchSize, file);
      } else {
        result = await uploadSingleResume(Number(jobId), file);
      }
      setRunId(result.run_id);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-8">Screen Resumes</h1>

      <div className="space-y-6 p-6 bg-zinc-900 border border-zinc-800 rounded-xl">
        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Job</label>
          <select
            value={jobId}
            onChange={(e) => setJobId(Number(e.target.value))}
            className="w-full px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none"
          >
            <option value="">Select a job</option>
            {jobs.map((j) => (
              <option key={j.job_id} value={j.job_id}>{j.job_title}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">Upload Mode</label>
          <div className="flex gap-3">
            <button
              onClick={() => { setMode("zip"); setFile(null); }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === "zip" ? "bg-cyan-600" : "bg-zinc-800 border border-zinc-700 hover:border-zinc-500"
              }`}
            >
              Zip (Bulk)
            </button>
            <button
              onClick={() => { setMode("single"); setFile(null); }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === "single" ? "bg-cyan-600" : "bg-zinc-800 border border-zinc-700 hover:border-zinc-500"
              }`}
            >
              Single Resume
            </button>
          </div>
        </div>

        {mode === "zip" && (
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">Batch Size</label>
            <input
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
              min={1}
              max={50}
              className="w-32 px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none"
            />
          </div>
        )}

        <div>
          <label className="block text-sm text-zinc-400 mb-1.5">
            {mode === "zip" ? "Resume Zip File" : "Resume (PDF or DOCX)"}
          </label>
          <input
            type="file"
            accept={mode === "zip" ? ".zip" : ".pdf,.docx"}
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm text-zinc-400 file:mr-4 file:px-4 file:py-2 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-zinc-800 file:text-zinc-300 hover:file:bg-zinc-700"
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={!jobId || !file || uploading}
          className="w-full py-2.5 bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          {uploading ? "Uploading..." : "Start Screening"}
        </button>
      </div>

      {/* Run Status */}
      {status && (
        <div className="mt-6 p-5 bg-zinc-900 border border-zinc-800 rounded-xl">
          <div className="flex items-center gap-3 mb-3">
            <span className={`w-2 h-2 rounded-full ${
              status.status === "completed" ? "bg-emerald-500" :
              status.status === "crashed" ? "bg-red-500" :
              "bg-amber-500 animate-pulse"
            }`} />
            <span className="text-sm font-medium capitalize">{status.status}</span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold">{status.total_resumes}</div>
              <div className="text-xs text-zinc-500">Total</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-emerald-400">{status.processed_count}</div>
              <div className="text-xs text-zinc-500">Processed</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-red-400">{status.failed_count}</div>
              <div className="text-xs text-zinc-500">Failed</div>
            </div>
          </div>
          {status.status === "running" && (
            <div className="mt-4 w-full bg-zinc-800 rounded-full h-2">
              <div
                className="bg-cyan-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${status.total_resumes ? (status.processed_count / status.total_resumes) * 100 : 0}%` }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
