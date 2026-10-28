import { ChevronLeft, ChevronRight } from 'lucide-react';

import { Button } from '@/shared/ui/button';

/** Переключатель страниц галереи: «Страница N из M». Не показывается, если страница одна. */
export function PagerNav({
  currentPage,
  totalPageCount,
  onPrev,
  onNext,
}: {
  currentPage: number;
  totalPageCount: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (totalPageCount <= 1) return null;
  return (
    <nav aria-label="Страницы галереи" className="flex items-center justify-center gap-3 py-2">
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label="Предыдущая страница"
        onClick={onPrev}
        disabled={currentPage <= 1}
      >
        <ChevronLeft />
      </Button>
      <span className="text-sm tabular-nums" aria-live="polite">
        Страница {currentPage} из {totalPageCount}
      </span>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label="Следующая страница"
        onClick={onNext}
        disabled={currentPage >= totalPageCount}
      >
        <ChevronRight />
      </Button>
    </nav>
  );
}
