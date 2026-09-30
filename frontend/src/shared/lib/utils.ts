import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Объединение классов Tailwind без конфликтов (соглашение shadcn/ui). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
