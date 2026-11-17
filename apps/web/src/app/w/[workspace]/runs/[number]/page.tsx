"use client";

import { useParams } from "next/navigation";

import { RunDetailView } from "@/components/runs/run-detail";

export default function RunPage() {
  const { number } = useParams<{ number: string }>();
  return <RunDetailView number={Number(number)} />;
}
