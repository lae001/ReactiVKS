import { Outlet } from 'react-router';

import { EmotionSpectrum, Wordmark } from '@/shared/ui/brand';

/** Экраны входа и регистрации: форма слева, пояснение о приватности справа. */
export function AuthLayout() {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
      <div className="flex flex-col px-6 py-8 md:px-12">
        <Wordmark />
        <main className="flex flex-1 items-center">
          <div className="w-full max-w-sm">
            <Outlet />
          </div>
        </main>
      </div>
      <aside className="hidden flex-col justify-end gap-6 bg-room p-12 text-room-foreground lg:flex">
        <EmotionSpectrum className="h-1.5 w-24" />
        <p className="text-xl leading-snug font-medium">
          Видите реакцию собеседников, даже когда смотрите в свои слайды.
        </p>
        <p className="text-sm leading-relaxed text-room-muted">
          Анализ включается только с согласия участника. Видео не записывается и не хранится —
          сохраняются лишь посекундные итоги распознавания для отчета организатору.
        </p>
      </aside>
    </div>
  );
}
