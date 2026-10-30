import { redirect } from "next/navigation";

// Scene generation now lives in each case's Incident Reconstruction Studio
// (authenticated, per-case); this standalone route is kept only so old links
// don't 404.
export default function ScenePage() {
  redirect("/");
}
