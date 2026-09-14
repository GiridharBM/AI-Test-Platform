import { Link, Outlet } from 'react-router-dom'

export function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <Link to="/" className="font-semibold tracking-tight">
            Auto Testing Platform
          </Link>
          <Link to="/" className="text-sm text-slate-400 hover:text-slate-200">
            Dashboard
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}