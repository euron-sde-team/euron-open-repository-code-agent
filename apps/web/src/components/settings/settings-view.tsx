"use client";

import { Suspense } from "react";

import { AccountPanel } from "@/components/settings/account-panel";
import { ActivityPanel } from "@/components/settings/activity-panel";
import { ApiKeysPanel } from "@/components/settings/api-keys-panel";
import { EnginePanel } from "@/components/settings/engine-panel";
import { GeneralPanel } from "@/components/settings/general-panel";
import { MembersPanel } from "@/components/settings/members-panel";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUrlParams } from "@/lib/use-url-params";
import { useActiveWorkspace } from "@/lib/workspace-context";

const TABS = [
  { value: "general", label: "General" },
  { value: "members", label: "People" },
  { value: "keys", label: "API keys", owner: true },
  { value: "engine", label: "Engine and sandbox" },
  { value: "activity", label: "Activity", owner: true },
  { value: "account", label: "Account" },
] as const;

function SettingsBody() {
  const { can, name } = useActiveWorkspace();
  const { get, update } = useUrlParams();
  const visible = TABS.filter((tab) => !("owner" in tab) || can("owner"));
  const requested = get("tab");
  const tab = visible.find((t) => t.value === requested)?.value ?? "general";
  return (
    <PageBody className="max-w-4xl">
      <PageHeader title="Settings" description={`${name}: people, access, and how the agent behaves.`} />
      <Tabs value={tab} onValueChange={(value) => update({ tab: value === "general" ? null : value })}>
        <TabsList aria-label="Settings sections">
          {visible.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="general">
          <GeneralPanel />
        </TabsContent>
        <TabsContent value="members">
          <MembersPanel />
        </TabsContent>
        {can("owner") ? (
          <TabsContent value="keys">
            <ApiKeysPanel />
          </TabsContent>
        ) : null}
        <TabsContent value="engine">
          <EnginePanel />
        </TabsContent>
        {can("owner") ? (
          <TabsContent value="activity">
            <ActivityPanel />
          </TabsContent>
        ) : null}
        <TabsContent value="account">
          <AccountPanel />
        </TabsContent>
      </Tabs>
    </PageBody>
  );
}

export function SettingsView() {
  return (
    <Suspense>
      <SettingsBody />
    </Suspense>
  );
}
