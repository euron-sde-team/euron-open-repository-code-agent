"use client";

import { useParams } from "next/navigation";

import { CodeBrowser } from "@/components/code/code-browser";

export default function CodeFilePage() {
  const { repo, path } = useParams<{ repo: string; path: string[] }>();
  return <CodeBrowser repo={decodeURIComponent(repo)} path={path.map(decodeURIComponent).join("/")} />;
}
