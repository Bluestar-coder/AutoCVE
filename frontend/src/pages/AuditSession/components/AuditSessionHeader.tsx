import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AuditSessionDetail } from "@/pages/AuditSession/types";

export function AuditSessionHeader({ session }: { session: AuditSessionDetail }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-xl">Audit Session</CardTitle>
            <p className="text-sm text-muted-foreground">Session {session.id}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">{session.runtime_stack}</Badge>
            <Badge>{session.state}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm text-muted-foreground md:grid-cols-2">
        <div>Project: {session.project_id}</div>
        <div>Task: {session.task_id || "unbound"}</div>
        <div>Created: {new Date(session.created_at).toLocaleString()}</div>
        <div>Updated: {new Date(session.updated_at).toLocaleString()}</div>
      </CardContent>
    </Card>
  );
}
