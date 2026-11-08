/**
 * Sidebar / settings icon for dsh-yuelan. An open book with a wave line,
 * drawn inline so the plugin ships no binary assets.
 * @module dsh-yuelan/client/icon
 */

import type { ReactNode } from 'react'

/** The 24×24 stroke icon. */
export function YuelanIcon({ size = 20, active = false }: { size?: number; active?: boolean }): ReactNode {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ opacity: active ? 1 : 0.85 }}
    >
      <path d="M12 5.5C10 4 7.5 3.5 4.5 3.5v15c3 0 5.5.5 7.5 2 2-1.5 4.5-2 7.5-2v-15c-3 0-5.5.5-7.5 2Z" />
      <path d="M12 5.5v15" />
      <path d="M7 9.5c1.2.2 2.2.6 3 1.2M7 13c1.2.2 2.2.6 3 1.2" />
    </svg>
  )
}
