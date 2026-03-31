"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  fetchJob,
  fetchResults,
  bulkUpdateDecision,
  updateDecision,
  getExportUrl,
} from "@/lib/api";

type JobDetail = { job_id: number; job_title: string; job_config: object; version: number };
type Result = {
  result_id: number;
  candidate_id: number | null;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  job_title: string;
  passed_out_year: number | null;
  score: number | null;
  decision: string | null;
  decision_reason: string | null;
  processed_at: string;
};

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const jobId = Number(params.id);
  const [job, setJob] = useState<JobDetail | null>(null);
  const [results, setResults] = useState<Result[]>([]);
  const [search, setSearch] = useState("");
  const [filterDecision, setFilterDecision] = useState("");
  const [minScore, setMinScore] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [showConfig, setShowConfig] = useState(false);

  const loadResults = useCallback(async () => {
    const data = await fetchResults(jobId, {
      search: search || undefined,
      decision: filterDecision || undefined,
      min_score: minScore ? Number(minScore) : undefined,
    });
    setResults(data);
  }, [jobId, search, filterDecision, minScore]);

  useEffect(() => {
    fetchJob(jobId).then(setJob);
    loadResults();
  }, [jobId, loadResults]);

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === results.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(results.map((r) => r.result_id)));
    }
  };

  const handleBulkAction = async (decision: string) => {
    if (selected.size === 0) return;
    await bulkUpdateDecision(Array.from(selected), decision);
    setSelected(new Set());
    loadResults();
  };

  const handleSingleDecision = async (resultId: number, decision: string) => {
    await updateDecision(resultId, decision);
    loadResults();
  };

  if (!job) return <div className="text-zinc-500">Loading...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{job.job_title}</h1>
          <span className="text-xs text-zinc-500">Version {job.version} &middot; {results.length} results</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowConfig(!showConfig)}
            className="px-3 py-1.5 text-sm border border-zinc-700 rounded-lg hover:border-zinc-500 transition-colors"
          >
            {showConfig ? "Hide Config" : "View Config"}
          </button>
          <a
            href={getExportUrl(jobId, filterDecision || undefined, minScore ? Number(minScore) : undefined)}
            className="px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-700 rounded-lg hover:border-zinc-500 transition-colors"
            target="_blank"
          >
            Export CSV
          </a>
        </div>
      </div>

      {showConfig && (
        <pre className="mb-6 p-4 bg-zinc-900 border border-zinc-800 rounded-xl text-xs overflow-auto max-h-64 text-zinc-300">
          {JSON.stringify(job.job_config, null, 2)}
        </pre>
      )}

      {/* Filters */}
      <div className="flex gap-3 mb-6 flex-wrap">
        <input
          type="text"
          placeholder="Search name or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadResults()}
          className="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm w-64 focus:outline-none focus:border-cyan-500"
        />
        <select
          value={filterDecision}
          onChange={(e) => { setFilterDecision(e.target.value); }}
          className="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm focus:outline-none"
        >
          <option value="">All Decisions</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="rejected">Rejected</option>
        </select>
        <input
          type="number"
          placeholder="Min Score"
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
          className="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm w-28 focus:outline-none"
        />
        <button
          onClick={loadResults}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded-lg text-sm font-medium transition-colors"
        >
          Search
        </button>
      </div>

      {/* Bulk Actions */}
      {selected.size > 0 && (
        <div className="mb-4 flex gap-3 items-center p-3 bg-zinc-900 border border-zinc-800 rounded-lg">
          <span className="text-sm text-zinc-400">{selected.size} selected</span>
          <button
            onClick={() => handleBulkAction("shortlisted")}
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-xs font-medium transition-colors"
          >
            Shortlist
          </button>
          <button
            onClick={() => handleBulkAction("rejected")}
            className="px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-xs font-medium transition-colors"
          >
            Reject
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="px-3 py-1.5 border border-zinc-700 rounded text-xs transition-colors hover:border-zinc-500"
          >
            Clear
          </button>
        </div>
      )}

      {/* Results Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-400 text-left">
              <th className="py-3 px-2 w-8">
                <input type="checkbox" checked={selected.size === results.length && results.length > 0} onChange={toggleAll} className="accent-cyan-500" />
              </th>
              <th className="py-3 px-2">Name</th>
              <th className="py-3 px-2">Email</th>
              <th className="py-3 px-2">Phone</th>
              <th className="py-3 px-2 text-center">Score</th>
              <th className="py-3 px-2 text-center">Year</th>
              <th className="py-3 px-2 text-center">Decision</th>
              <th className="py-3 px-2">Reason</th>
              <th className="py-3 px-2 w-20"></th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.result_id} className="border-b border-zinc-800/50 hover:bg-zinc-900/50">
                <td className="py-3 px-2">
                  <input
                    type="checkbox"
                    checked={selected.has(r.result_id)}
                    onChange={() => toggleSelect(r.result_id)}
                    className="accent-cyan-500"
                  />
                </td>
                <td className="py-3 px-2 font-medium">{r.full_name || "\u2014"}</td>
                <td className="py-3 px-2 text-zinc-400">{r.email || "\u2014"}</td>
                <td className="py-3 px-2 text-zinc-400">{r.phone || "\u2014"}</td>
                <td className="py-3 px-2 text-center">
                  <span className={`font-mono font-medium ${(r.score ?? 0) >= 60 ? "text-emerald-400" : "text-red-400"}`}>
                    {r.score ?? "\u2014"}
                  </span>
                </td>
                <td className="py-3 px-2 text-center text-zinc-400">{r.passed_out_year || "\u2014"}</td>
                <td className="py-3 px-2 text-center">
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      r.decision === "shortlisted"
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "bg-red-500/15 text-red-400"
                    }`}
                  >
                    {r.decision || "\u2014"}
                  </span>
                </td>
                <td className="py-3 px-2 text-xs text-zinc-500 max-w-xs truncate">{r.decision_reason || ""}</td>
                <td className="py-3 px-2">
                  <div className="flex gap-1">
                    {r.decision !== "shortlisted" && (
                      <button
                        onClick={() => handleSingleDecision(r.result_id, "shortlisted")}
                        className="px-2 py-1 text-xs text-emerald-400 hover:bg-emerald-500/10 rounded transition-colors"
                        title="Shortlist"
                      >
                        &#10003;
                      </button>
                    )}
                    {r.decision !== "rejected" && (
                      <button
                        onClick={() => handleSingleDecision(r.result_id, "rejected")}
                        className="px-2 py-1 text-xs text-red-400 hover:bg-red-500/10 rounded transition-colors"
                        title="Reject"
                      >
                        &#10007;
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {results.length === 0 && (
          <div className="text-center text-zinc-500 py-12">No results yet. Upload resumes to start screening.</div>
        )}
      </div>
    </div>
  );
}
