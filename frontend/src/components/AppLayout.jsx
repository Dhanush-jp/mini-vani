import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function AppLayout() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-6 px-4 py-6 lg:flex-row lg:px-6">
        <Sidebar />
        <main className="flex-1 space-y-6 pb-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
