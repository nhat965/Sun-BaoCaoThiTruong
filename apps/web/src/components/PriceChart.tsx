"use client";

import dynamic from "next/dynamic";
import type { PriceBar } from "@/lib/types";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function PriceChart({ bars }: { bars: PriceBar[] }) {
  const visible = bars.slice(-120);
  const option = {
    animation: false,
    grid: { left: 16, right: 16, top: 24, bottom: 36, containLabel: true },
    tooltip: { trigger: "axis", valueFormatter: (value: number) => value.toLocaleString("vi-VN") },
    xAxis: { type: "category", boundaryGap: false, data: visible.map((bar) => bar.timestamp.slice(0, 10)), axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (value: number) => `${Math.round(value / 1000)}k` }, splitLine: { lineStyle: { type: "dashed" } } },
    series: [{ name: "Đóng cửa", type: "line", showSymbol: false, smooth: false, data: visible.map((bar) => bar.close), lineStyle: { width: 2 }, areaStyle: { opacity: .08 } }],
  };
  return <ReactECharts option={option} style={{ height: 340, width: "100%" }} aria-label="Biểu đồ giá đóng cửa 120 phiên gần nhất" />;
}

