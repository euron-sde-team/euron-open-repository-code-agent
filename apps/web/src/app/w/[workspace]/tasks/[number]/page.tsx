"use client";

import { useParams } from "next/navigation";

import { TaskDetailView } from "@/components/tasks/task-detail";

export default function TaskPage() {
  const { number } = useParams<{ number: string }>();
  return <TaskDetailView number={Number(number)} />;
}
