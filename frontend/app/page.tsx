import { CompanySearch } from "@/components/company-search";

export default function Home() {
  return (
    <main className="app-shell">
      <header className="border-b border-ink/10 bg-bone/90 px-4 py-4 backdrop-blur sm:px-6 lg:px-10">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div>
            <div className="eyebrow text-brass">AlphaLens</div>
            <h1 className="mt-1 text-2xl font-black tracking-normal text-ink">
              SEC Research Console
            </h1>
          </div>
          <div className="hidden rounded-lg border border-line bg-paper px-3 py-2 text-sm font-semibold text-moss sm:block">
            Source-grounded SEC research
          </div>
        </div>
      </header>
      <CompanySearch />
    </main>
  );
}
