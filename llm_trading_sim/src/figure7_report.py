"""Export reusable descriptive findings and static scientific figures."""
import csv

def fmt(x): return 'NA' if x is None else f'{x:.3f}'

def write_report(data,out):
    lines=['# Figure 7 与估值—报价差距复核','',
           '数据来自已有运行文件；此分析工具不调用 GPT。估值按 agent × 轮次去重，市价单的日志价格不作为自主限价报价。',
           '轮次从原始决策的 0–14 映射为展示的 1–15。缺失/非正估值不填零。10% 是本次描述性阈值，不是从论文推导的收敛检验。','',
           '|运行|决策行数→agent-round|首轮估值中位数|末轮估值中位数|末轮距基本价值≤10%的比例|限价报价的 agent-round 中位差距 / V|',
           '|---|---:|---:|---:|---:|---:|']
    for run in data['runs']:
        v=run['valuation_analysis']
        if 'overall' not in v:continue
        first,last=v['round_summary'][0],v['round_summary'][-1]
        lines.append(f"|{run['id']}|{v['source_rows']} → {len(v['agent_rounds'])}|{fmt(first['valuation_median'])}|{fmt(last['valuation_median'])}|{fmt(last['fraction_within_10pct'])}|{fmt(v['overall']['median_agent_round_quote_gap'])}|")
    lines.extend(['','## 2026-10-13 至 15 六组历史运行的具体发现','',
        '- 六组运行的首轮与末轮估值中位数均为 $28；每组末轮 6/8 个 agent 的估值在 $28 的 ±10% 内。中位数并未表现出逐渐向 $28 调整的过程。',
        '- 每组末轮仍有两位 optimistic agent 高估。首组高估运行中两人的末轮估值分别为 $41.6 和 $96；其他运行的乐观型末轮估值为 $40 或 $41.6。',
        '- 因此，高估持续与准确估值可以同时出现，角色异质性被总体中位数掩盖。是否偏离论文的个体轨迹，需要保留无作者原图数值这一限制。',
        '- 有效限价报价与估值仍有明显距离。不能从这组描述性结果直接推断因果锚定或系统性羊群效应。',
        '','## 解释范围','',
        '- 初始两次 baseline 与队友新增 baseline 分开呈现；不能把某一批的估值特征推广到所有运行。',
        '- 估值趋向 $28 与报价/成交趋向 $28 是不同结果。报价差距只覆盖有效限价单，未下限价单的 agent-round 不进入该差距统计。',
        '- “更接近上一轮记录价格”只是一种描述性现象，不证明价格锚定的因果机制；该参考价本身可能来自报价。',
        '- 一个运行内的多个 agent 和轮次不视为独立重复实验；未计算伪独立显著性。',
        '- 仍未取得作者原图数据，不能声明逐点重现 Figure 7。',
        '- 独立随机数与重放功能改变了实验控制方式，新的受控运行应与旧 legacy 运行分开标注。'])
    (out/'figure7_findings.md').write_text('\n'.join(lines))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    count=len(data['runs']); nrows=max(1,(count+1)//2)
    fig,axs=plt.subplots(nrows,2,figsize=(12,3.7*nrows),sharex=True,squeeze=False)
    roles={'default':'#41745b','optimistic':'#c4823c','market_maker':'#497eaf','speculator':'#9265a7'}
    for ax,run in zip(axs.flat,data['runs']):
        v=run['valuation_analysis'];pts=v.get('agent_rounds',[])
        for agent in sorted({p['agent_id'] for p in pts}):
            ps=[p for p in pts if p['agent_id']==agent];role=ps[0]['agent_type']
            ax.plot([p['round'] for p in ps],[p['valuation'] if p['valuation'] is not None else float('nan') for p in ps],color=roles.get(role,'gray'),alpha=.65,linewidth=1.1)
        ax.axhline(28,color='black',linestyle='--',linewidth=1)
        ax.set_title(run['id']+' | start $'+str(run['parameters']['INITIAL_PRICE']),fontsize=10)
        ax.set_ylabel('Reported valuation ($)');ax.grid(alpha=.15)
    for ax in list(axs.flat)[count:]:ax.set_visible(False)
    for ax in axs[-1]:ax.set_xlabel('Round (display, 1-based)')
    handles=[plt.Line2D([0],[0],color=c,label=r) for r,c in roles.items()]
    fig.legend(handles=handles,loc='lower center',ncol=4)
    fig.suptitle(f'Figure 7 audit: individual beliefs, {count} saved runs',fontsize=15)
    fig.tight_layout(rect=(0,.035,1,.96));fig.savefig(out/'figure7_valuation_audit.png',dpi=170);fig.savefig(out/'figure7_valuation_audit.svg');plt.close(fig)
