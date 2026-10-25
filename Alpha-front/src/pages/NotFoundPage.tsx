import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-6 text-center">
      <p className="text-sm font-medium text-gray-500">404</p>
      <h1 className="mt-2 text-2xl font-bold text-gray-900">
        Страница не найдена
      </h1>
      <p className="mt-2 text-gray-600">
        Такой страницы нет или она была перемещена.
      </p>
      <Button asChild className="mt-6">
        <Link to="/">На главную</Link>
      </Button>
    </div>
  )
}
