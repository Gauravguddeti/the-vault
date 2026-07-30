import { auth } from "@/auth";
import { redirect } from "next/navigation";
import AppShell from "@/components/AppShell";
import PageTransition from "@/components/PageTransition";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) redirect("/login");
  return (
    <AppShell>
      <PageTransition>{children}</PageTransition>
    </AppShell>
  );
}
