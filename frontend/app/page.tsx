import { CompanySearch } from "@/components/company-search";

export default function Home() {
  return (
    <main className="min-h-screen bg-paper">
      <header className="border-b border-ink/10 bg-ink px-4 py-5 text-white sm:px-6 lg:px-10">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div>
            <div className="text-sm font-semibold uppercase tracking-wide text-brass">AlphaLens</div>
            <h1 className="mt-1 text-2xl font-semibold">Research Dashboard</h1>
          </div>
          <div className="hidden rounded-lg border border-white/15 px-3 py-2 text-sm text-white/80 sm:block">
            Milestone 1
          </div>
        </div>
      </header>
      <CompanySearch />
    </main>
  );
}
