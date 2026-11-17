"use client";

import { useParams } from "next/navigation";

import { CodeBrowser } from "@/components/code/code-browser";

export default function CodeIndexPage() {
  const { repo } = useParams<{ repo: string }>();
  return <CodeBrowser repo={decodeURIComponent(repo)} path={null} />;
}
