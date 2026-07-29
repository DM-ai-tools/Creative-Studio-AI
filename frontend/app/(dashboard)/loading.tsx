export default function DashboardLoading() {
  return (
    <div className="p-6 md:p-8 space-y-6 max-w-[1600px] animate-pulse">
      <div className="h-8 w-48 rounded-lg bg-light" />
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 rounded-xl bg-light" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 h-80 rounded-xl bg-light" />
        <div className="h-80 rounded-xl bg-light" />
      </div>
    </div>
  )
}
