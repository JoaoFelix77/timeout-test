import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

# 读取并聚合
df = pd.read_csv("results/logs.csv")             #根据结果实际存储位置修改
sub = df[(df.Mode=="DrissionPage-chrome") & (df.Concurrency==2)]             #根据实际模式与并发量修改
stats = sub.groupby("Timeout(s)").agg({
    "P50Success(s)": "mean",
    "SuccessRate": "mean"
}).reset_index()

# 转换成功率为百分比
stats["SuccessRatePct"] = stats["SuccessRate"] * 100

# 绘图
fig, ax1 = plt.subplots(figsize=(8, 5))
ax2 = ax1.twinx()

# P50 曲线：蓝色实线 + 圆点
ax1.plot(
    stats["Timeout(s)"], stats["P50Success(s)"],
    color='blue', linestyle='-', linewidth=2, marker='o', markersize=6,
    label="P50 Success Time"
)

# 成功率曲线：红色虚线 + 三角点
ax2.plot(
    stats["Timeout(s)"], stats["SuccessRatePct"],
    color='red', linestyle='--', linewidth=2, marker='^', markersize=6,
    label="SuccessRate"
)

# 坐标轴标签
ax1.set_xlabel("Timeout (s)", fontsize=12)
ax1.set_ylabel("P50 Success Time (s)", fontsize=12, color='blue')
ax2.set_ylabel("Success Rate (%)", fontsize=12, color='red')

# 设置 success rate 轴范围与刻度
ax2.set_ylim(0, 100)
ax2.yaxis.set_major_locator(mtick.MultipleLocator(10))
ax2.yaxis.set_minor_locator(mtick.MultipleLocator(5))
ax2.yaxis.set_major_formatter(mtick.PercentFormatter())

# 网格
ax1.grid(which='both', linestyle=':', linewidth=0.5)

# 图例放在顶部中央，横向排列，并移出图形
handles1, labels1 = ax1.get_legend_handles_labels()
handles2, labels2 = ax2.get_legend_handles_labels()
plt.legend(
    handles1 + handles2,
    labels1 + labels2,
    loc='upper center',
    bbox_to_anchor=(0.5, 1.15),
    ncol=2,
    frameon=False,
    fontsize=10
)

plt.title("Timeout vs Time & Success Rate", fontsize=14)
plt.tight_layout()
plt.show()
