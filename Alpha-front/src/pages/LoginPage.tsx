import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/contexts/AuthContext'
import { getApiErrorMessage } from '@/lib/api'

const demoAccounts = [
  { label: 'Клиент', email: 'client@demo.ru' },
  { label: 'Банк', email: 'bank@demo.ru' },
]

function homeForRole(role: 'client' | 'bank') {
  return role === 'bank' ? '/bank' : '/applications'
}

export function LoginPage() {
  const { user, token, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (token && user) {
    return <Navigate to={homeForRole(user.role)} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const nextUser = await login(email, password)
      navigate(homeForRole(nextUser.role), { replace: true })
    } catch (cause) {
      setError(
        getApiErrorMessage(
          cause,
          cause instanceof Error ? cause.message : 'Не удалось войти',
        ),
      )
    } finally {
      setLoading(false)
    }
  }

  function fillDemo(demoEmail: string) {
    setEmail(demoEmail)
    setPassword('password123')
    setError(null)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-6 py-10">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Вход в кабинет</CardTitle>
          <CardDescription>
            Умный кредитный кабинет предпринимателя
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.ru"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {error ? (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            ) : null}

            <Button className="w-full" type="submit" disabled={loading}>
              {loading ? <Loader2 className="animate-spin" /> : null}
              Войти
            </Button>
          </form>

          <div className="mt-6 rounded-md bg-gray-50 p-4">
            <p className="text-sm text-gray-600">
              Демо: client@demo.ru / password123 (клиент), bank@demo.ru /
              password123 (банк)
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {demoAccounts.map((account) => (
                <Button
                  key={account.email}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fillDemo(account.email)}
                >
                  Заполнить: {account.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
