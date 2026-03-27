/**
 * Feature Guide content for Dashboard sections.
 * Supports en, zh, pt. Do not hardcode long text in components.
 */

export type FeatureGuideLocale = "en" | "zh" | "pt";

export interface FeatureGuideSection {
  title: string;
  text: string;
  actions?: string;
}

/** Macro Data: overview, category, news, index, philosophy */
export interface MacroGuideContent {
  buttonLabel: string;
  modalTitle: string;
  overview: FeatureGuideSection;
  category: FeatureGuideSection;
  news: FeatureGuideSection;
  index: FeatureGuideSection;
  philosophy: FeatureGuideSection;
}

/** Target Data: overview, portfolios, targets, monitoring, interaction, philosophy */
export interface EntityGuideContent {
  buttonLabel: string;
  modalTitle: string;
  overview: FeatureGuideSection;
  portfolios: FeatureGuideSection;
  entities: FeatureGuideSection;
  monitoring: FeatureGuideSection;
  interaction: FeatureGuideSection;
  philosophy: FeatureGuideSection;
}

const macroDataContent: Record<FeatureGuideLocale, MacroGuideContent> = {
  en: {
    buttonLabel: "Macro Guide",
    modalTitle: "Macro Data — Feature Guide",
    overview: {
      title: "Overview",
      text: "This section provides a real-time view of macro-level and category-specific market narratives. It combines news flow, market data, and activity signals to help you understand what the market is focusing on.",
    },
    category: {
      title: "Category Selector",
      text: "Switch between different market segments such as General, Stocks, Futures, and Crypto. You can also create your own custom categories to track specific narratives, industries, or themes.",
    },
    news: {
      title: "News List",
      text: "Displays recent news related to the selected category. Each item may include sentiment and impact indicators to help you quickly assess relevance, tone, and possible market significance.",
    },
    index: {
      title: "Index Watchlist",
      text: "Shows key market indices and assets such as S&P 500, NASDAQ, Oil, Gold, and VIX. You can customize this list to track the indices or assets most relevant to your own focus.",
    },
    philosophy: {
      title: "Data Philosophy",
      text: "All indicators are designed to remain neutral and data-driven. The system does not provide direct investment advice. Its purpose is to help users interpret market narratives, sentiment, and activity signals more clearly.",
    },
  },
  zh: {
    buttonLabel: "宏观说明",
    modalTitle: "宏观数据 — 功能说明",
    overview: {
      title: "整体说明",
      text: "该模块用于展示宏观层面及细分市场的实时舆情与市场动态，通过整合新闻流、市场数据和活跃度信号，帮助你快速理解当前市场关注点。",
    },
    category: {
      title: "分类选择",
      text: "你可以在 General、Stock、Futures、Crypto 等不同类别之间切换，也可以自定义创建分类，用于跟踪特定行业、主题或叙事方向。",
    },
    news: {
      title: "新闻列表",
      text: "这里展示当前分类下的相关新闻流。每条新闻可附带情绪和影响力指标，帮助你更快判断其重要性、倾向和潜在市场相关性。",
    },
    index: {
      title: "指数监控",
      text: "这里显示关键市场指数及资产，例如标普500、纳斯达克、原油、黄金和VIX等。你也可以自定义添加自己想长期观察的指数或资产。",
    },
    philosophy: {
      title: "数据原则",
      text: "所有指标都应保持中立和数据驱动，系统不直接提供投资建议。它的目标是帮助用户更清晰地理解市场叙事、情绪变化和活跃度信号。",
    },
  },
  pt: {
    buttonLabel: "Guia Macro",
    modalTitle: "Dados Macro — Guia de Funções",
    overview: {
      title: "Visão Geral",
      text: "Esta seção oferece uma visão em tempo real das narrativas de mercado em nível macro e por categoria. Ela combina fluxo de notícias, dados de mercado e sinais de atividade para mostrar onde está o foco do mercado.",
    },
    category: {
      title: "Seletor de Categoria",
      text: "Alterne entre diferentes segmentos como Geral, Ações, Futuros e Cripto. Você também pode criar categorias personalizadas para acompanhar temas, setores ou narrativas específicas.",
    },
    news: {
      title: "Lista de Notícias",
      text: "Exibe notícias recentes relacionadas à categoria selecionada. Cada item pode incluir indicadores de sentimento e impacto para ajudar a avaliar relevância, tom e possível importância para o mercado.",
    },
    index: {
      title: "Lista de Índices",
      text: "Mostra índices e ativos importantes como S&P 500, NASDAQ, Petróleo, Ouro e VIX. Você também pode personalizar essa lista para acompanhar os ativos mais relevantes para você.",
    },
    philosophy: {
      title: "Filosofia de Dados",
      text: "Todos os indicadores são neutros e orientados por dados. O sistema não fornece aconselhamento direto de investimento. Seu objetivo é ajudar o usuário a interpretar melhor narrativas, sentimento e sinais de atividade do mercado.",
    },
  },
};

const entityDataContent: Record<FeatureGuideLocale, EntityGuideContent> = {
  en: {
    buttonLabel: "Target Guide",
    modalTitle: "Target Data — Feature Guide",
    overview: {
      title: "Overview",
      text: "This section is used to organize and monitor custom portfolios and targets. It helps users group related assets, narratives, or themes into a more focused tracking structure.",
    },
    portfolios: {
      title: "Portfolios",
      text: "Portfolios are used as containers for different monitoring groups. You can create and manage separate portfolio spaces for different strategies, sectors, or research directions.",
    },
    entities: {
      title: "Target List",
      text: "This area displays the targets currently stored inside the selected portfolio. Each target usually represents a specific company, asset, or narrative object being tracked.",
    },
    monitoring: {
      title: "Monitoring Logic",
      text: "Target Data is designed for more focused tracking than Macro Data. Instead of looking at broad market categories, this page helps you follow specific targets in a structured way.",
    },
    interaction: {
      title: "Interaction with Periodic Monitoring",
      text: "Target Data and Periodic Monitoring work together. You define targets here (companies, assets, narrative themes), then configure scheduled monitoring runs in the Periodic Monitoring section. Those runs will scan and track your targets at the intervals you set, and generate reports that appear in Reports.",
    },
    philosophy: {
      title: "Data Philosophy",
      text: "The goal of this page is to help users organize and observe target-specific information more clearly. It is a research and monitoring tool, not a direct investment recommendation system.",
    },
  },
  zh: {
    buttonLabel: "目标说明",
    modalTitle: "目标数据 — 功能说明",
    overview: {
      title: "整体说明",
      text: "该模块用于组织和监控自定义的投资组合与目标，帮助用户将相关资产、叙事或主题放入更聚焦的跟踪结构中。",
    },
    portfolios: {
      title: "投资组合",
      text: "Portfolio 用来承载不同的监控分组。你可以为不同策略、行业或研究方向分别建立独立的组合空间。",
    },
    entities: {
      title: "目标列表",
      text: "这里展示当前所选 Portfolio 下的各个目标。每个目标通常代表一个具体公司、资产，或一个需要持续跟踪的叙事对象。",
    },
    monitoring: {
      title: "监控逻辑",
      text: "目标数据相比宏观数据更偏向聚焦式跟踪。它不是观察大范围市场分类，而是帮助你更有结构地追踪具体目标。",
    },
    interaction: {
      title: "与定期监控的联动",
      text: "目标数据与定期监控相互配合。你在此处定义目标（公司、资产、叙事主题），然后在「定期监控」中配置监控任务。这些任务将按你设定的周期扫描并跟踪目标，并生成报告显示在「报告」中。",
    },
    philosophy: {
      title: "数据原则",
      text: "该页面的目标是帮助用户更清晰地组织和观察特定目标的信息。它属于研究与监控工具，而不是直接给出投资建议的系统。",
    },
  },
  pt: {
    buttonLabel: "Guia de Alvos",
    modalTitle: "Dados de Alvos — Guia de Funções",
    overview: {
      title: "Visão Geral",
      text: "Esta seção é usada para organizar e monitorar portfólios e alvos personalizados. Ela ajuda o usuário a agrupar ativos, narrativas ou temas em uma estrutura de acompanhamento mais focada.",
    },
    portfolios: {
      title: "Portfólios",
      text: "Os portfólios funcionam como contêineres para diferentes grupos de monitoramento. Você pode criar espaços separados para diferentes estratégias, setores ou linhas de pesquisa.",
    },
    entities: {
      title: "Lista de Alvos",
      text: "Esta área mostra os alvos atualmente armazenados dentro do portfólio selecionado. Cada alvo normalmente representa uma empresa, ativo ou objeto narrativo específico em acompanhamento.",
    },
    monitoring: {
      title: "Lógica de Monitoramento",
      text: "Dados de Alvos foi projetado para um acompanhamento mais focado do que Dados Macro. Em vez de observar categorias amplas de mercado, esta página ajuda a seguir alvos específicos de forma estruturada.",
    },
    interaction: {
      title: "Interação com Monitoramento Periódico",
      text: "Dados de Alvos e Monitoramento Periódico funcionam em conjunto. Você define os alvos aqui (empresas, ativos, temas narrativos) e configura as execuções de monitoramento agendadas na seção Monitoramento Periódico. Essas execuções escaneiam e acompanham seus alvos nos intervalos definidos, gerando relatórios que aparecem em Relatórios.",
    },
    philosophy: {
      title: "Filosofia de Dados",
      text: "O objetivo desta página é ajudar o usuário a organizar e observar informações específicas de forma mais clara. Trata-se de uma ferramenta de pesquisa e monitoramento, não de um sistema de recomendação direta de investimento.",
    },
  },
};

/** Entity Data vs Research conceptual guide (What is this?) */
export interface EntityConceptGuideContent {
  buttonLabel: string;
  modalTitle: string;
  entityData: FeatureGuideSection;
  research: FeatureGuideSection;
  difference: FeatureGuideSection;
  why: FeatureGuideSection;
  principle: FeatureGuideSection;
}

const entityConceptGuideContent: Record<FeatureGuideLocale, EntityConceptGuideContent> = {
  en: {
    buttonLabel: "What is this?",
    modalTitle: "Entity Data vs Research",
    entityData: {
      title: "What is Entity Data?",
      text: "Entity Data is a structured monitoring system for specific targets. Each entity represents a company, asset, theme, or narrative object that you want to track continuously over time.",
    },
    research: {
      title: "What is Research?",
      text: "Research is a flexible analysis workspace. It is used for temporary comparison, chart analysis, indicator testing, and deeper investigation of selected targets.",
    },
    difference: {
      title: "Core Difference",
      text: "Entity Data is for long-term tracking. Research is for temporary analysis. Entity Data stores and organizes what you want to keep watching, while Research is where you actively study and compare those targets.",
    },
    why: {
      title: "Why Both Exist",
      text: "The product separates monitoring from analysis. This makes the structure clearer: Entity Data helps you maintain stable target lists, while Research gives you a more flexible space for charts, comparisons, and deeper exploration.",
    },
    principle: {
      title: "Simple Usage Principle",
      text: "Use Entity Data when you want to save and monitor a target over time. Use Research when you want to analyze, compare, or experiment with charts and indicators.",
    },
  },
  zh: {
    buttonLabel: "这是什么？",
    modalTitle: "目标数据 与 Research 的区别",
    entityData: {
      title: "什么是目标数据？",
      text: "目标数据（Entity Data）是一个面向特定目标的结构化监控系统。每个 Entity 都代表一个你希望长期跟踪的公司、资产、主题，或叙事对象。",
    },
    research: {
      title: "什么是 Research？",
      text: "Research 是一个灵活的分析工作台，用于临时性的对比、图表分析、指标测试，以及对特定目标进行更深入的研究。",
    },
    difference: {
      title: "核心区别",
      text: "目标数据用于长期跟踪，Research 用于临时分析。目标数据负责保存和组织你想持续观察的对象，而 Research 是你主动研究、对比和拆解这些对象的地方。",
    },
    why: {
      title: "为什么两者都存在？",
      text: "这个产品将「监控」和「分析」分开处理，以保持结构清晰。目标数据帮助你维护稳定的跟踪对象列表，而 Research 提供更灵活的空间来进行图表、对比和深入探索。",
    },
    principle: {
      title: "简单使用原则",
      text: "当你想长期保存并监控一个目标时，用目标数据；当你想分析、对比或实验图表与指标时，用 Research。",
    },
  },
  pt: {
    buttonLabel: "O que é isto?",
    modalTitle: "Entity Data vs Research",
    entityData: {
      title: "O que é Entity Data?",
      text: "Entity Data é um sistema estruturado de monitoramento para alvos específicos. Cada entidade representa uma empresa, ativo, tema ou objeto narrativo que você deseja acompanhar continuamente ao longo do tempo.",
    },
    research: {
      title: "O que é Research?",
      text: "Research é um espaço flexível de análise. Ele é usado para comparação temporária, análise de gráficos, testes de indicadores e investigação mais profunda de alvos selecionados.",
    },
    difference: {
      title: "Diferença Principal",
      text: "Entity Data é para acompanhamento de longo prazo. Research é para análise temporária. Entity Data organiza e armazena o que você deseja continuar monitorando, enquanto Research é o espaço onde você estuda e compara esses alvos.",
    },
    why: {
      title: "Por que os dois existem?",
      text: "O produto separa monitoramento de análise para manter a estrutura mais clara. Entity Data ajuda a manter listas estáveis de alvos, enquanto Research oferece um espaço mais flexível para gráficos, comparações e exploração mais profunda.",
    },
    principle: {
      title: "Princípio de Uso Simples",
      text: "Use Entity Data quando quiser salvar e monitorar um alvo ao longo do tempo. Use Research quando quiser analisar, comparar ou experimentar gráficos e indicadores.",
    },
  },
};

export const featureGuideContent = {
  macroData: macroDataContent,
  entityData: entityDataContent,
  entityConcept: entityConceptGuideContent,
};
