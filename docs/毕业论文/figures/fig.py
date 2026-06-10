# # import matplotlib.pyplot as plt
# # import numpy as np

# # # 支持中文显示
# # plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'Microsoft YaHei']
# # plt.rcParams['axes.unicode_minus'] = False

# # # 1. 准备数据
# # approaches = ['TraceRCA', 'NetEventCause', 'BiAn', 'Ours']
# # y_pos = np.arange(len(approaches))
# # bar_width = 0.25

# # # Normal Cases 数据
# # normal_top1 = [14.44, 60.00, 48.89, 60.00]
# # normal_top2 = [22.22, 80.00, 64.44, 84.44]
# # normal_top3 = [24.44, 86.67, 67.78, 92.22]

# # # Storm Cases 数据
# # storm_top1 = [7.14, 14.29, 21.43, 35.71]
# # storm_top2 = [7.14, 21.43, 28.57, 64.29]
# # storm_top3 = [7.14, 28.57, 35.71, 78.57]

# # # 2. 创建画布 (1行2列的分面图)
# # fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
# # colors = ['#aec7e8', '#1f77b4', '#0f4c81'] # 蓝渐变色系，可自行调整

# # # ---- 左图：Normal Cases ----
# # ax1.barh(y_pos + bar_width, normal_top3, bar_width, label='Top-3 Acc', color=colors[0])
# # ax1.barh(y_pos, normal_top2, bar_width, label='Top-2 Acc', color=colors[1])
# # ax1.barh(y_pos - bar_width, normal_top1, bar_width, label='Top-1 Acc', color=colors[2])

# # ax1.set_title('Normal Cases', fontsize=14, fontweight='bold', pad=15)
# # ax1.set_xlabel('Accuracy (%)', fontsize=12)
# # ax1.set_yticks(y_pos)
# # ax1.set_yticklabels(approaches, fontsize=12)
# # ax1.set_xlim(0, 105)
# # ax1.grid(axis='x', linestyle='--', alpha=0.5)

# # # 在柱状图上添加数据标签
# # for i in range(len(approaches)):
# #     ax1.text(normal_top3[i] + 1, i + bar_width, f'{normal_top3[i]:.1f}', va='center', fontsize=9)
# #     ax1.text(normal_top2[i] + 1, i, f'{normal_top2[i]:.1f}', va='center', fontsize=9, color='white', fontweight='bold' if i==3 else 'normal')
# #     ax1.text(normal_top1[i] + 1, i - bar_width, f'{normal_top1[i]:.1f}', va='center', fontsize=9)

# # # ---- 右图：Storm Cases ----
# # ax2.barh(y_pos + bar_width, storm_top3, bar_width, label='Top-3 Acc', color=colors[0])
# # ax2.barh(y_pos, storm_top2, bar_width, label='Top-2 Acc', color=colors[1])
# # ax2.barh(y_pos - bar_width, storm_top1, bar_width, label='Top-1 Acc', color=colors[2])

# # ax2.set_title('Storm Cases', fontsize=14, fontweight='bold', pad=15)
# # ax2.set_xlabel('Accuracy (%)', fontsize=12)
# # ax2.set_xlim(0, 105)
# # ax2.grid(axis='x', linestyle='--', alpha=0.5)

# # # 在柱状图上添加数据标签
# # for i in range(len(approaches)):
# #     ax2.text(storm_top3[i] + 1, i + bar_width, f'{storm_top3[i]:.1f}', va='center', fontsize=9)
# #     ax2.text(storm_top2[i] + 1, i, f'{storm_top2[i]:.1f}', va='center', fontsize=9)
# #     ax2.text(storm_top1[i] + 1, i - bar_width, f'{storm_top1[i]:.1f}', va='center', fontsize=9)

# # # ---- 全局调整 ----
# # #plt.gca().invert_yaxis() # 让 'Ours' 呈现在最上方或最下方（这里保持原表格顺序，Ours在最下，如需Ours在最上可启用这行）
# # ax1.legend(loc='lower right')
# # plt.tight_layout()

# # # 显示图表
# # plt.show()

# import matplotlib.pyplot as plt
# import numpy as np

# # 支持中文显示
# plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'Microsoft YaHei']
# plt.rcParams['axes.unicode_minus'] = False

# # 1. 准备消融实验数据
# paradigms = ['LLM', 'LLM+ 告警权重', 'PageRank', 'LLM+ 告警权重 +PageRank']
# y_pos = np.arange(len(paradigms))
# bar_width = 0.24

# # Normal Cases 数据
# normal_top1 = [51.11, 54.40, 38.89, 60.00]
# normal_top2 = [73.33, 78.89, 70.00, 84.44]
# normal_top3 = [75.56, 85.56, 77.78, 92.22]

# # Storm Cases 数据
# storm_top1 = [7.14, 28.57, 28.57, 35.71]
# storm_top2 = [14.29, 28.57, 57.14, 64.29]
# storm_top3 = [21.43, 42.86, 64.29, 78.57]

# # 2. 创建画布 (1行2列)
# fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6.5), sharey=True)

# # 选用一组更有学术/科技感的渐变绿色/青色系（与前一张图做视觉区分）
# colors = ['#a1d99b', '#41ab5d', '#006d2c'] 

# # ---- 左图：Normal Cases ----
# ax1.barh(y_pos + bar_width, normal_top3, bar_width, label='Top-3 Acc', color=colors[0])
# ax1.barh(y_pos, normal_top2, bar_width, label='Top-2 Acc', color=colors[1])
# ax1.barh(y_pos - bar_width, normal_top1, bar_width, label='Top-1 Acc', color=colors[2])

# ax1.set_title('Normal Cases ', fontsize=14, fontweight='bold', pad=15)
# ax1.set_xlabel('Accuracy (%)', fontsize=12)
# ax1.set_yticks(y_pos)
# ax1.set_yticklabels(paradigms, fontsize=11)
# ax1.set_xlim(0, 105)
# ax1.grid(axis='x', linestyle='--', alpha=0.5)

# # 添加数据标签
# for i in range(len(paradigms)):
#     ax1.text(normal_top3[i] + 1, i + bar_width, f'{normal_top3[i]:.1f}', va='center', fontsize=9.5)
#     ax1.text(normal_top2[i] + 1, i, f'{normal_top2[i]:.1f}', va='center', fontsize=9.5)
#     ax1.text(normal_top1[i] + 1, i - bar_width, f'{normal_top1[i]:.1f}', va='center', fontsize=9.5)

# # ---- 右图：Storm Cases ----
# ax2.barh(y_pos + bar_width, storm_top3, bar_width, label='Top-3 Acc', color=colors[0])
# ax2.barh(y_pos, storm_top2, bar_width, label='Top-2 Acc', color=colors[1])
# ax2.barh(y_pos - bar_width, storm_top1, bar_width, label='Top-1 Acc', color=colors[2])

# ax2.set_title('Storm Cases ', fontsize=14, fontweight='bold', pad=15)
# ax2.set_xlabel('Accuracy (%)', fontsize=12)
# ax2.set_xlim(0, 105)
# ax2.grid(axis='x', linestyle='--', alpha=0.5)

# # 添加数据标签
# for i in range(len(paradigms)):
#     ax2.text(storm_top3[i] + 1, i + bar_width, f'{storm_top3[i]:.1f}', va='center', fontsize=9.5)
#     ax2.text(storm_top2[i] + 1, i, f'{storm_top2[i]:.1f}', va='center', fontsize=9.5)
#     ax2.text(storm_top1[i] + 1, i - bar_width, f'{storm_top1[i]:.1f}', va='center', fontsize=9.5)

# # ---- 全局优化 ----
# ax1.legend(loc='lower right', fontsize=10)
# plt.tight_layout()

# # 显示图表
# plt.show()
import matplotlib.pyplot as plt
import numpy as np

# 支持中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 1. 按照指定的新顺序准备基座模型数据（从上到下显示）
models = [
    'DeepSeek-R1-Distill-Qwen-32B (32B)',
    'DeepSeek-R1-Distill-Qwen-14B (14B)',
    'DeepSeek-R1-Distill-Qwen-7B (7B)',
    'Qwen2.5-32B-Instruct (32B)',
    'Qwen2.5-14B-Instruct (14B)'
]
y_pos = np.arange(len(models))
bar_width = 0.24

# 对应新顺序的 Normal Cases 数据
normal_top1 = [60.00, 47.78, 12.22, 53.33, 42.22]
normal_top2 = [84.44, 68.89, 18.89, 74.44, 56.67]
normal_top3 = [92.22, 71.11, 21.11, 75.56, 56.67]

# 对应新顺序的 Storm Cases 数据
storm_top1 = [35.71, 7.14, 0.00, 14.29, 7.14]
storm_top2 = [64.29, 14.29, 0.00, 14.29, 7.14]
storm_top3 = [78.57, 14.29, 0.00, 21.43, 14.29]

# 2. 创建画布 (1行2列)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7), sharey=True)

# 选用富有科技感的紫色/冷色调渐变
colors = ['#cbc9e2', '#9e9ac8', '#6a51a3']

# ---- 左图：Normal Cases ----
ax1.barh(y_pos + bar_width, normal_top3, bar_width, label='Top-3 Acc', color=colors[0])
ax1.barh(y_pos, normal_top2, bar_width, label='Top-2 Acc', color=colors[1])
ax1.barh(y_pos - bar_width, normal_top1, bar_width, label='Top-1 Acc', color=colors[2])

ax1.set_title('Normal Cases (基座模型对比)', fontsize=14, fontweight='bold', pad=15)
ax1.set_xlabel('Accuracy (%)', fontsize=12)
ax1.set_yticks(y_pos)
ax1.set_yticklabels(models, fontsize=10)
ax1.set_xlim(0, 105)
ax1.grid(axis='x', linestyle='--', alpha=0.5)

# 添加数据标签
for i in range(len(models)):
    ax1.text(normal_top3[i] + 1, i + bar_width, f'{normal_top3[i]:.1f}', va='center', fontsize=9)
    ax1.text(normal_top2[i] + 1, i, f'{normal_top2[i]:.1f}', va='center', fontsize=9)
    ax1.text(normal_top1[i] + 1, i - bar_width, f'{normal_top1[i]:.1f}', va='center', fontsize=9)

# ---- 右图：Storm Cases ----
ax2.barh(y_pos + bar_width, storm_top3, bar_width, label='Top-3 Acc', color=colors[0])
ax2.barh(y_pos, storm_top2, bar_width, label='Top-2 Acc', color=colors[1])
ax2.barh(y_pos - bar_width, storm_top1, bar_width, label='Top-1 Acc', color=colors[2])

ax2.set_title('Storm Cases (基座模型对比)', fontsize=14, fontweight='bold', pad=15)
ax2.set_xlabel('Accuracy (%)', fontsize=12)
ax2.set_xlim(0, 105)
ax2.grid(axis='x', linestyle='--', alpha=0.5)

# 添加数据标签
for i in range(len(models)):
    # 针对 7B 模型在 Storm 场景下全为 0 的情况做特殊留白处理
    if storm_top3[i] == 0:
        ax2.text(1, i, '0.0', va='center', fontsize=9, color='gray')
        continue
    ax2.text(storm_top3[i] + 1, i + bar_width, f'{storm_top3[i]:.1f}', va='center', fontsize=9)
    ax2.text(storm_top2[i] + 1, i, f'{storm_top2[i]:.1f}', va='center', fontsize=9)
    ax2.text(storm_top1[i] + 1, i - bar_width, f'{storm_top1[i]:.1f}', va='center', fontsize=9)

# ---- 全局优化 ----
ax1.invert_yaxis()  # 反转Y轴，确保图形严格按列表从上到下的顺序渲染
ax1.legend(loc='lower right', fontsize=10)
plt.tight_layout()

# 显示图表
plt.show()