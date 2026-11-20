'use client'

import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'

/**
 * Page transition for every dashboard page. A template (unlike a layout) is created fresh on each
 * navigation, so the new page eases in while the sidebar stays still. It settles on `transform: none`,
 * so pop-ups and sticky bars inside a page are not affected afterwards, and it does nothing when the
 * person has asked their system for reduced motion.
 */
export default function DashboardTemplate({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      className="h-full"
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}
