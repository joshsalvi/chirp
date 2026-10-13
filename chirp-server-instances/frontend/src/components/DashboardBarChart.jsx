import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

/**
 * The Dashboard's two bar charts, in a separate lazy chunk so the Dashboard
 * (the first page most visits load) renders without waiting for Recharts.
 *
 * cellFill: optional (row, index) => color per bar; otherwise fill.
 */
export default function DashboardBarChart({
  data, xKey = 'label', yKey, tooltip, fill, cellFill, cellOpacity,
  tickSize = 10, yWidth = 24, interval = 'preserveStartEnd', margin, gap = '12%',
  radius = [4, 4, 0, 0], debounce,
}) {
  const tick = { fontSize: tickSize, fill: 'var(--text-tertiary)', fontFamily: 'DM Sans' }
  return (
    <ResponsiveContainer width="100%" height="100%" debounce={debounce}>
      <BarChart data={data} margin={margin} barCategoryGap={gap}>
        <XAxis dataKey={xKey} tick={tick} tickLine={false} axisLine={false} interval={interval}/>
        <YAxis tick={tick} tickLine={false} axisLine={false} width={yWidth} allowDecimals={false}/>
        <Tooltip content={tooltip} cursor={{ fill: 'rgba(255,255,255,.03)', radius: 4 }}/>
        <Bar dataKey={yKey} radius={radius} fill={cellFill ? undefined : fill}>
          {cellFill && data.map((d, i) => (
            <Cell key={i} fill={cellFill(d, i)} opacity={cellOpacity ? cellOpacity(d, i) : 1}/>
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
