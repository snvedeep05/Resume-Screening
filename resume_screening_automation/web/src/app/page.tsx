"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchJobs, createJob, generateJobConfig } from "@/lib/api";

type Job = { job_id: number; job_title: string; version: number };

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [jd, setJd] = useState("");
  const [generating, setGenerating] = useState(false);
  const [config, setConfig] = useState<object | null>(null);

  useEffect(() => {
    fetchJobs().then(setJobs);
  }, []);

  const handleGenerate = async () => {
    if (!jd.trim()) return;
    setGenerating(true);
    try {
      const result = await generateJobConfig(jd);
      setConfig(result.job_config);
    } finally {
      setGenerating(false);
    }
  };

  const handleCreate = async () => {
    if (!title.trim() || !config) return;
    await createJob(title, config);
    setShowCreate(false);
    setTitle("");
    setJd("");
    setConfig(null);
    fetchJobs().then(setJobs);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Jobs</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded-lg text-sm font-medium transition-colors"
        >
          + New Job
        </button>
      </div>

      {showCreate && (
        <div className="mb-8 p-6 bg-zinc-900 border border-zinc-800 rounded-xl space-y-4">
          <input
            type="text"
            placeholder="Job Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full px-4 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500"
          />
          <textarea
            placeholder="Paste the job description here..."
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            rows={6}
            className="w-full px-4 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500 resize-y"
          />
          <div className="flex gap-3">
            <button
              onClick={handleGenerate}
              disabled={generating || !jd.trim()}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
            >
              {generating ? "Generating..." : "AI Generate Config"}
            </button>
            {config && (
              <button
                onClick={handleCreate}
                disabled={!title.trim()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
              >
                Create Job
              </button>
            )}
          </div>
          {config && (
            <pre className="mt-4 p-4 bg-zinc-800 rounded-lg text-xs overflow-auto max-h-64 text-zinc-300">
              {JSON.stringify(config, null, 2)}
            </pre>
          )}
        </div>
      )}

      <div className="grid gap-4">
        {jobs.map((job) => (
          <Link
            key={job.job_id}
            href={`/jobs/${job.job_id}`}
            className="block p-5 bg-zinc-900 border border-zinc-800 rounded-xl hover:border-zinc-600 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{job.job_title}</div>
                <div className="text-xs text-zinc-500 mt-1">Version {job.version}</div>
              </div>
              <span className="text-zinc-500 text-sm">{"->"}</span>
            </div>
          </Link>
        ))}
        {jobs.length === 0 && (
          <div className="text-center text-zinc-500 py-12">No jobs yet. Create one to get started.</div>
        )}
      </div>
    </div>
  );
}
