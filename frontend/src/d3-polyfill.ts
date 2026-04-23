/**
 * Runtime polyfill for d3-selection's missing `interrupt` method.
 *
 * Rollup creates multiple copies of d3-selection's Selection class when
 * different d3 packages (d3-zoom, d3-drag, d3-transition) each import it.
 * d3-transition's side-effect augmentation (`Selection.prototype.interrupt = ...`)
 * only patches ONE copy, but reactflow's d3-zoom may use a DIFFERENT copy.
 *
 * This polyfill imports `select` from d3-selection, creates a selection,
 * and patches its actual prototype with `interrupt` if missing.
 */
import { select } from 'd3-selection'

const el = document.createElement('div')
const sel = select(el)
const proto = Object.getPrototypeOf(sel)

if (typeof proto.interrupt !== 'function') {
  proto.interrupt = function (this: any, name?: string) {
    return this.each(function (this: any) {
      const schedules = this.__transition
      if (schedules) {
        const key = name ? `${name}__transition` : null
        for (const id in schedules) {
          const s = schedules[id]
          if (!key || s.name === key) {
            s.state = 6 // ENDED
            s.timer.stop()
            if (s.on?.interrupt) {
              s.on.interrupt.call(this, this.__data__, s.index, s.group)
            }
            delete schedules[id]
          }
        }
        if (!Object.keys(schedules).length) {
          delete this.__transition
        }
      }
    })
  }
}
