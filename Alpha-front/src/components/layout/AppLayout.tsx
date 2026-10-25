import { useState } from 'react'
import { Link, Outlet, useNavigate } from 'react-router-dom'
import { LogOut, Plus, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  const initial = user?.email.trim().charAt(0).toUpperCase() || '?'

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-50 border-b border-gray-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-3 px-4 sm:px-6">
          <Link
            to="/"
            onClick={() => setUserMenuOpen(false)}
            className="flex shrink-0 items-center gap-2 text-lg font-semibold text-gray-900 transition-colors duration-150 hover:text-gray-700"
          >
            <Sparkles className="h-5 w-5 text-indigo-600" />
            Суирники3
          </Link>

          <div className="flex items-center gap-2 sm:gap-3">
            <Button
              asChild
              className="bg-gray-900 text-white hover:bg-gray-800"
            >
              <Link to="/applications/new">
                <Plus />
                <span className="sm:hidden">Создать</span>
                <span className="hidden sm:inline">Создать заявку</span>
              </Link>
            </Button>

            <span className="hidden h-5 w-px bg-gray-200 md:block" />
            <span className="hidden max-w-56 truncate text-sm text-gray-600 md:block">
              {user?.email}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="hidden md:inline-flex"
              onClick={handleLogout}
            >
              <LogOut />
              Выйти
            </Button>

            <div className="relative md:hidden">
              <button
                type="button"
                className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-full bg-indigo-50 text-sm font-semibold text-indigo-600 transition-colors duration-150 hover:bg-indigo-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
                aria-label="Профиль"
                aria-expanded={userMenuOpen}
                onClick={() => setUserMenuOpen((value) => !value)}
              >
                {initial}
              </button>

              {userMenuOpen ? (
                <div className="absolute right-0 mt-2 w-60 rounded-md border border-gray-200 bg-white p-3 shadow-lg">
                  <p className="truncate text-sm text-gray-600">
                    {user?.email}
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="mt-2 w-full justify-start"
                    onClick={handleLogout}
                  >
                    <LogOut />
                    Выйти
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
