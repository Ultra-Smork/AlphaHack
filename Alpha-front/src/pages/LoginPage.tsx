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
import { toast } from '@/hooks/use-toast'
import { getApiErrorMessage } from '@/lib/api'

const demoEmail = 'client@demo.ru'

export function LoginPage() {
  const { user, token, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (token && user) {
    return <Navigate to="/applications" replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setLoading(true)

    try {
      await login(email, password)
      navigate('/applications', { replace: true })
    } catch (cause) {
      const message = getApiErrorMessage(
        cause,
        cause instanceof Error ? cause.message : 'Не удалось войти',
      )
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  function fillDemo() {
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
              Демо: client@demo.ru / password123
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={fillDemo}
              >
                Заполнить демо
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
