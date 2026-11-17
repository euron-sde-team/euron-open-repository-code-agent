"use client";

import { useParams } from "next/navigation";

import { RepoDetail } from "@/components/repos/repo-detail";

export default function RepositoryPage() {
  const { repo } = useParams<{ repo: string }>();
  return <RepoDetail repo={decodeURIComponent(repo)} />;
}
