export type GuidePageKey =
  | 'overview'
  | 'targets'
  | 'clusters'
  | 'rules'
  | 'events'
  | 'channels'
  | 'records'
  | 'logs'
  | 'assistant'
  | 'grafana'
  | 'platformHealth';

export type GuideStep = {
  title: string;
  description: string;
};

export type GuideSection = {
  key: string;
  title: string;
  summary: string;
  page?: GuidePageKey;
  rootOnly?: boolean;
  prerequisites?: string[];
  steps?: GuideStep[];
  notes?: string[];
  example?: string;
  children?: GuideSection[];
};

type ExporterGuide = {
  key: string;
  title: string;
  endpoint: string;
  preparation: string;
  start: string;
  note: string;
};

const exporterGuides: ExporterGuide[] = [
  {
    key: 'node',
    title: 'Node Exporter（Linux 服务器）',
    endpoint: 'http://服务器IP:9100/metrics',
    preparation: '在被监控 Linux 服务器下载与系统架构匹配的 node_exporter，并为它创建 systemd 服务。',
    start: '启动 node_exporter，开放 TCP 9100，并确认从平台网络访问 /metrics 能返回 node_ 开头的指标。',
    note: '适合监控 CPU、内存、磁盘、负载和网络；不要把 9100 直接暴露给整个互联网。',
  },
  {
    key: 'mysql',
    title: 'MySQL / MariaDB Exporter',
    endpoint: 'http://服务器IP:9104/metrics',
    preparation: '在数据库中创建只读监控账号，下载 mysqld_exporter，并配置数据库地址、账号和密码。',
    start: '启动 mysqld_exporter，开放 TCP 9104，先在目标服务器本地验证 /metrics，再从平台网络验证。',
    note: '监控账号只授予采集状态所需权限，不要使用 root 数据库账号。',
  },
  {
    key: 'nginx',
    title: 'Nginx Exporter',
    endpoint: 'http://服务器IP:9113/metrics',
    preparation: '在现有 Nginx 中启用仅供监控访问的 stub_status 地址，例如 /nginx_status；不需要再安装一套 Nginx。',
    start: '启动 nginx-prometheus-exporter，并让它读取 http://127.0.0.1/nginx_status，随后开放 TCP 9113。',
    note: 'stub_status 应限制来源 IP；平台填写的是 Exporter 的 9113/metrics，不是 nginx_status 地址。',
  },
  {
    key: 'redis',
    title: 'Redis Exporter',
    endpoint: 'http://服务器IP:9121/metrics',
    preparation: '下载 redis_exporter，配置 REDIS_ADDR；Redis 有密码或 TLS 时同时配置认证参数。',
    start: '启动 redis_exporter，开放 TCP 9121，并验证 /metrics 中存在 redis_up 和 redis_ 指标。',
    note: 'Exporter 应部署在能访问 Redis 的网络中，Redis 本身无需向平台公网开放。',
  },
  {
    key: 'postgresql',
    title: 'PostgreSQL Exporter',
    endpoint: 'http://服务器IP:9187/metrics',
    preparation: '创建只读监控用户，下载 postgres_exporter，并用 DATA_SOURCE_NAME 配置数据库连接。',
    start: '启动 Exporter，开放 TCP 9187，确认 pg_up 为 1 且 /metrics 可被平台访问。',
    note: '生产环境建议用 Secret 或环境文件保存密码，避免写在启动命令和仓库中。',
  },
  {
    key: 'mongodb',
    title: 'MongoDB Exporter',
    endpoint: 'http://服务器IP:9216/metrics',
    preparation: '创建最小权限监控账号，下载兼容当前 MongoDB 版本的 Exporter，并配置 MongoDB URI。',
    start: '启动 Exporter，开放 TCP 9216，检查 /metrics 中的 mongodb_up 和连接、操作指标。',
    note: '副本集需要在连接 URI 中写明成员和 replicaSet，并正确配置 TLS。',
  },
  {
    key: 'kafka',
    title: 'Kafka Exporter',
    endpoint: 'http://服务器IP:9308/metrics',
    preparation: '下载 kafka_exporter，配置一个或多个 Broker 地址；启用 SASL/TLS 时同时填写认证参数。',
    start: '启动 Exporter，开放 TCP 9308，确认能采集 Broker、Topic、Partition 和消费组延迟。',
    note: 'JVM、GC 等进程指标应另外使用 JMX Exporter；Kafka Exporter 更侧重集群和消费组。',
  },
  {
    key: 'rabbitmq',
    title: 'RabbitMQ Exporter',
    endpoint: 'http://服务器IP:15692/metrics',
    preparation: 'RabbitMQ 3.8 及以上可直接启用 rabbitmq_prometheus 插件，无需另装第三方 Exporter。',
    start: '执行 rabbitmq-plugins enable rabbitmq_prometheus，映射或开放 TCP 15692，并验证 /metrics。',
    note: '队列级明细可查看 /metrics/per-object；大规模队列会产生更多序列，应控制采集频率。',
  },
  {
    key: 'elasticsearch',
    title: 'Elasticsearch Exporter',
    endpoint: 'http://服务器IP:9114/metrics',
    preparation: '下载 elasticsearch_exporter，配置可访问 Elasticsearch 的 ES_URI 和只读认证信息。',
    start: '启动 Exporter，开放 TCP 9114，验证集群健康、节点、JVM、分片和存储指标。',
    note: '启用集群和索引级采集会增加查询负担，只开启实际需要的采集项。',
  },
  {
    key: 'clickhouse',
    title: 'ClickHouse Exporter',
    endpoint: 'http://服务器IP:9363/metrics',
    preparation: '优先启用 ClickHouse 自带 Prometheus endpoint，或部署与当前版本兼容的 ClickHouse Exporter。',
    start: '配置监听地址和 9363 端口，确认 /metrics 返回 Prometheus 文本格式，然后开放平台到该端口。',
    note: '不同 ClickHouse 版本的内置端口和配置项可能不同，以实际配置文件为准。',
  },
  {
    key: 'zookeeper',
    title: 'ZooKeeper Exporter',
    endpoint: 'http://服务器IP:9141/metrics',
    preparation: '部署 ZooKeeper Exporter，或为 ZooKeeper JVM 配置 JMX Exporter，并限制 four-letter-word 管理命令访问。',
    start: '让 Exporter 连接 ZooKeeper，开放 TCP 9141，确认连接数、请求、znode 和延迟指标可用。',
    note: '不要为了采集指标将 ZooKeeper 客户端端口直接暴露到公网。',
  },
  {
    key: 'etcd',
    title: 'etcd 指标',
    endpoint: 'https://服务器IP:2379/metrics',
    preparation: 'etcd 自带 /metrics；确认监听地址允许采集，并准备客户端证书、CA 和密钥（如启用双向 TLS）。',
    start: '从受信网络验证 /metrics，开放平台或采集代理到 2379 的访问，再在平台添加地址。',
    note: '2379 是高敏感管理端口，推荐通过专线、VPN、代理或 Agent 采集，禁止直接公网开放。',
  },
  {
    key: 'blackbox',
    title: 'Blackbox Exporter',
    endpoint: 'http://服务器IP:9115/metrics',
    preparation: '下载 blackbox_exporter，并在 blackbox.yml 中配置 HTTP、TCP、ICMP 或 DNS 探测模块。',
    start: '启动 Exporter 并开放 TCP 9115；注册 Exporter 本身时填写 /metrics，网站和端口仍建议用平台对应类型添加。',
    note: '完整探测指标来自 /probe?module=...&target=...；需要平台 Prometheus 使用参数化采集配置。',
  },
  {
    key: 'cadvisor',
    title: 'cAdvisor（容器）',
    endpoint: 'http://服务器IP:8080/metrics',
    preparation: '以容器方式运行 cAdvisor，并按官方要求只读挂载宿主机根目录、Docker/containerd 数据目录。',
    start: '启动 cAdvisor，开放 TCP 8080，确认 /metrics 中存在 container_cpu 和 container_memory 指标。',
    note: '宿主机挂载权限较高，应限制镜像来源、网络访问和运行权限。',
  },
  {
    key: 'windows',
    title: 'Windows Exporter',
    endpoint: 'http://服务器IP:9182/metrics',
    preparation: '在 Windows 服务器安装 windows_exporter MSI，并选择 CPU、内存、磁盘、网络、服务等采集器。',
    start: '确认 Windows 服务正在运行，在防火墙中仅允许平台来源访问 TCP 9182，并验证 /metrics。',
    note: '采集器开启越多，指标量越大；先开启常用采集器，再按需增加。',
  },
  {
    key: 'process',
    title: 'Process Exporter',
    endpoint: 'http://服务器IP:9256/metrics',
    preparation: '下载 process-exporter，并在 YAML 中按进程名、命令行或可执行文件定义 process_names 分组。',
    start: '启动 Exporter，开放 TCP 9256，确认指定进程出现 CPU、内存、线程和文件描述符指标。',
    note: '分组规则应保持稳定，避免把 PID 等动态值写入标签造成大量时间序列。',
  },
  {
    key: 'jmx',
    title: 'JMX Exporter（Java 中间件）',
    endpoint: 'http://服务器IP:9404/metrics',
    preparation: '下载 jmx_prometheus_javaagent 和规则 YAML，将 javaagent 参数加入 Java 应用启动参数。',
    start: '重启 Java 应用，开放 TCP 9404，确认 JVM、GC、线程池及中间件专属指标可访问。',
    note: '修改 Java 启动参数会重启业务，生产环境应安排变更窗口并先在测试环境验证规则。',
  },
  {
    key: 'custom',
    title: '自定义 Prometheus Exporter',
    endpoint: 'http://服务器IP:自定义端口/metrics',
    preparation: '让应用或自研 Exporter 按 Prometheus 文本格式暴露指标，指标名和标签保持稳定。',
    start: '用 curl 验证 /metrics 返回 200 和 # HELP、# TYPE、指标样本，再开放平台访问并添加 Target。',
    note: '不要将用户 ID、请求 ID 等高基数字段作为标签，否则会导致 Prometheus 序列快速增长。',
  },
];

const exporterSections: GuideSection[] = exporterGuides.map((exporter) => ({
  key: `targets-exporter-${exporter.key}`,
  title: exporter.title,
  page: 'targets',
  summary: `将 ${exporter.title} 暴露的 Prometheus 指标接入平台持续采集。`,
  prerequisites: [
    '平台后端或 Prometheus 能访问 Exporter 地址；私网目标需要 VPN、专线、反向代理或集群 Agent 打通网络。',
    '安全组、防火墙和容器端口映射已只对必要来源放行。',
  ],
  steps: [
    { title: '准备采集端', description: exporter.preparation },
    { title: '启动并验证', description: exporter.start },
    { title: '在平台添加', description: `进入“监控对象”，类型选“Exporter”，再选择“${exporter.title}”，地址填写 ${exporter.endpoint}。` },
    { title: '检测和同步采集', description: '保存后执行手动检测，确认状态正常；再点击同步采集，等待 Prometheus 完成首次抓取。' },
    { title: '配置图表与告警', description: '进入 Grafana 图表同步专属仪表盘，并在告警规则中选择该 Target 和对应指标。' },
  ],
  example: exporter.endpoint,
  notes: [exporter.note, '若 /metrics 本地可访问但平台检测失败，优先检查路由、防火墙、安全组、容器映射和 TLS 证书。'],
}));

export const guideSections: GuideSection[] = [
  {
    key: 'quick-start',
    title: '快速开始',
    page: 'overview',
    summary: '从添加第一个监控对象开始，完成检测、采集、告警、通知和图表查看。',
    steps: [
      { title: '确认网络', description: '确保平台能访问被监控地址；不要直接填写只有目标服务器本机才能访问的 127.0.0.1。' },
      { title: '添加监控对象', description: '网站选择完整 URL，端口填写“主机:端口”，中间件先部署 Exporter 再填写 /metrics。' },
      { title: '检查采集状态', description: '保存后先手动检测，再同步采集；Exporter 需要等待 Prometheus 首次抓取。' },
      { title: '创建告警规则', description: '选择监控范围、具体对象、指标、阈值、告警等级，并启用规则。' },
      { title: '配置通知渠道', description: '添加邮箱或机器人 Webhook，设置发送等级、触发/恢复通知和内容模板。' },
      { title: '处理告警事件', description: '在事件详情中确认、记录处置过程、用 AI 分析，并在恢复后关闭事件。' },
      { title: '查看日志和图表', description: '通过简单日志查询定位异常，再用 Grafana 查看趋势和相关指标。' },
    ],
    notes: ['建议先用一个可访问的网站或 Node Exporter 完成全流程测试，再批量接入业务。'],
  },
  {
    key: 'targets',
    title: '监控对象',
    page: 'targets',
    summary: '平台支持网站、TCP 端口和 Prometheus Exporter。先选择类型，再按对应格式填写地址。',
    steps: [
      { title: '进入监控对象', description: '点击左侧“监控对象”，在新增表单中填写便于识别的名称。' },
      { title: '选择监控类型', description: '网站用于 HTTP/HTTPS，端口用于 TCP 连通性，Exporter 用于服务器和中间件指标。' },
      { title: '保存并检测', description: '保存后点击检测；HTTP 400–599、连接失败、超时或指标格式错误会判为异常。' },
      { title: '同步持续采集', description: 'Exporter 检测成功后同步到 Prometheus，等待采集状态更新。' },
    ],
    children: [
      {
        key: 'targets-website',
        title: '网站监控',
        page: 'targets',
        summary: '检测 HTTP/HTTPS 可用性、响应时间、状态码、DNS、TLS 证书和页面关键字。',
        prerequisites: ['平台网络能访问该网站；如有限制，请将平台出口 IP 加入白名单。'],
        steps: [
          { title: '选择网站类型', description: '新增监控对象时选择“网站”。' },
          { title: '填写完整 URL', description: '必须包含 http:// 或 https://，并尽量使用健康检查路径。' },
          { title: '设置期望关键字', description: '可选填写页面中应出现的文本；关键字不存在时会判为异常。' },
          { title: '保存并检测', description: '查看 HTTP 状态码、响应时间、DNS 和 TLS 结果；400–599 默认判为异常。' },
          { title: '添加告警', description: '可针对不可用、响应时间、状态码、TLS 剩余天数或关键字不匹配创建规则。' },
        ],
        example: 'https://www.example.com/health',
        notes: ['需要登录才能访问的页面应提供独立、轻量且无需交互登录的健康检查地址。'],
      },
      {
        key: 'targets-port',
        title: 'TCP 端口监控',
        page: 'targets',
        summary: '检测 SSH、数据库、缓存、消息队列或其他 TCP 服务端口能否建立连接。',
        prerequisites: ['目标安全组和防火墙允许平台来源 IP 访问该端口。'],
        steps: [
          { title: '选择端口类型', description: '新增监控对象时选择“端口”。' },
          { title: '填写地址', description: '使用“主机:端口”格式，不要添加 http://、路径或多余空格。' },
          { title: '保存并检测', description: '平台会尝试建立 TCP 连接；连接成功不等于业务协议和账号一定正常。' },
          { title: '创建规则', description: '对“监控对象不可用”或响应时间创建告警规则。' },
        ],
        example: '10.0.0.8:6379',
        notes: ['数据库等敏感端口优先走内网、VPN 或代理，不建议直接向公网开放。'],
      },
      {
        key: 'targets-exporter',
        title: 'Exporter 指标监控',
        page: 'targets',
        summary: 'Exporter 把服务器或中间件状态转换为 Prometheus 指标。平台采集的是 Exporter，不是直接登录业务。',
        prerequisites: [
          '先在被监控服务器、中间件旁边或目标 Kubernetes 集群中安装或启用对应 Exporter。',
          '使用 curl 访问 /metrics，确认返回 HTTP 200 和 Prometheus 文本指标。',
        ],
        steps: [
          { title: '选择具体 Exporter', description: '根据操作系统或中间件选择下方细分类型。' },
          { title: '在目标环境部署', description: 'Exporter 应靠近业务部署，并使用最小权限账号连接中间件。' },
          { title: '打通采集网络', description: '仅允许平台、Prometheus 或 Agent 访问 Exporter 端口。' },
          { title: '在平台注册', description: '类型选“Exporter”，填写平台可访问的完整 /metrics URL。' },
          { title: '同步和验证', description: '检测成功后同步采集，并在 Grafana 和告警规则中验证指标。' },
        ],
        notes: ['选择下面的具体类型可查看对应准备方法、默认端口和验证步骤。'],
        children: exporterSections,
      },
    ],
  },
  {
    key: 'clusters',
    title: '集群管理',
    page: 'clusters',
    summary: '通过平台生成的 Agent 清单接入用户自己的 Kubernetes 集群，采集集群状态、事件和日志。',
    children: [
      {
        key: 'clusters-add',
        title: '添加集群',
        page: 'clusters',
        summary: '先在平台登记集群，生成独立 Token 和 Agent 安装清单。',
        steps: [
          { title: '填写集群信息', description: '填写名称、集群类型和说明；名称应能区分环境和地域。' },
          { title: '填写 API Server（可选）', description: 'Agent 运行在目标集群内部时可留空，它会使用 ServiceAccount 自动访问集群 API。' },
          { title: '保存集群', description: '平台会创建集群记录、专属 Agent Token 和安装命令。' },
          { title: '复制安装内容', description: '选择该集群后复制完整命令或 YAML；其中的平台 URL 必须能从目标集群访问。' },
        ],
        notes: ['每个集群使用自己的 Token，不要把一个集群的安装 YAML 复用到其他集群。'],
      },
      {
        key: 'clusters-agent',
        title: '安装 Agent',
        page: 'clusters',
        summary: '在被监控 Kubernetes 集群执行平台生成的命令，让 Agent 定期上报数据。',
        prerequisites: ['拥有目标集群 kubectl 管理权限。', '目标集群能访问平台 API URL，并能拉取 Agent 镜像。'],
        steps: [
          { title: '检查生成内容', description: '确认平台 API URL、Agent 镜像地址、命名空间和集群 Token 都属于当前环境。' },
          { title: '在目标集群执行', description: '把生成的 YAML 保存后 kubectl apply，或直接执行平台给出的安装命令。' },
          { title: '检查 Agent Pod', description: '执行 kubectl get pods 查看 Agent 是否 Running，并用 kubectl logs 排查错误。' },
          { title: '等待首次心跳', description: '通常 30–60 秒后平台显示在线，并出现节点、Pod、工作负载、事件和日志。' },
        ],
        notes: ['测试时可以把支撑平台的集群作为一个被监控集群，但生产环境应区分平台集群和客户集群。'],
      },
      {
        key: 'clusters-status',
        title: '查看集群状态',
        page: 'clusters',
        summary: '查看当前快照，而不是重复展示每次心跳产生的相同计数。',
        steps: [
          { title: '选择集群', description: '在集群列表中选中目标集群。' },
          { title: '检查在线状态', description: '先看最近心跳时间和 Agent 版本，离线时优先检查 Agent Pod 和网络。' },
          { title: '查看健康详情', description: '依次检查节点、工作负载、异常 Pod、资源、存储网络、Warning Event 和日志。' },
          { title: '处理异常', description: '根据事件或日志定位命名空间、Pod 和容器，再创建对应告警。' },
        ],
      },
    ],
  },
  {
    key: 'rules',
    title: '告警规则',
    page: 'rules',
    summary: '为节点资源或监控对象设置指标、比较条件、阈值和告警等级。',
    children: [
      {
        key: 'rules-node',
        title: '节点资源规则',
        page: 'rules',
        summary: '对 Node Exporter 上报的 CPU、内存、磁盘和负载创建阈值告警。',
        steps: [
          { title: '选择节点范围', description: '规则范围选择“节点”，再选择 CPU、内存、磁盘或负载指标。' },
          { title: '设置比较条件', description: '资源使用率通常使用 > 或 >=；阈值单位必须与页面指标单位一致。' },
          { title: '选择告警等级', description: '按影响程度设置一般、严重或紧急，通知渠道可按等级过滤。' },
          { title: '保存并启用', description: '保存后确认启用状态，并通过测试阈值观察是否生成事件。' },
        ],
      },
      {
        key: 'rules-target',
        title: '监控对象规则',
        page: 'rules',
        summary: '对网站、端口和各类 Exporter 的可用性或业务指标创建告警。',
        steps: [
          { title: '选择对象范围', description: '规则范围选择“监控对象”，再选择具体 Target。' },
          { title: '选择匹配指标', description: '网站可选状态码/TLS，端口可选不可用，Exporter 可选通用或中间件专属指标。' },
          { title: '设置阈值和等级', description: '根据业务基线设置条件，先观察正常范围，避免直接使用不合理的固定阈值。' },
          { title: '验证告警链路', description: '短暂使用测试阈值触发一次，确认事件、通知和恢复通知都能工作。' },
        ],
        notes: ['计数器类指标通常应使用速率或增量判断；若页面只提供原值，请避免直接对累计总数设置长期固定阈值。'],
      },
    ],
  },
  {
    key: 'events',
    title: '告警事件',
    page: 'events',
    summary: '查看正在发生和已恢复的告警，并留下完整的确认、排查和处置记录。',
    steps: [
      { title: '筛选事件', description: '按状态、等级、实例或规则查找事件，优先处理紧急且未确认的告警。' },
      { title: '打开详情', description: '查看当前值、阈值、触发次数、最近触发时间和相关通知记录。' },
      { title: '确认和分派', description: '点击确认告警并更新处理状态，避免多人重复处理。' },
      { title: '分析和记录', description: '添加排查记录，可跳转 AI 助手或 Grafana 获取更多上下文。' },
      { title: '恢复和关闭', description: '指标恢复后核实业务状态，记录结论并将事件标记为恢复或关闭。' },
    ],
  },
  {
    key: 'channels',
    title: '通知渠道',
    page: 'channels',
    summary: '把符合等级和触发条件的告警真正发送到邮箱、钉钉、飞书、企业微信或通用 Webhook。',
    children: [
      {
        key: 'channels-email',
        title: '邮箱通知',
        page: 'channels',
        summary: '使用用户自己的 SMTP 服务发送可编辑的触发和恢复邮件。',
        prerequisites: ['准备 SMTP 主机、端口、发件账号和邮箱授权码；授权码通常不是登录密码。'],
        steps: [
          { title: '选择邮箱类型', description: '填写渠道名称、收件人邮箱和发件人信息。' },
          { title: '配置 SMTP', description: '填写服务器、端口、账号、授权码以及 SSL/TLS 选项。' },
          { title: '设置发送规则', description: '选择一般/严重/紧急等级，并决定触发和恢复时是否发送。' },
          { title: '编辑模板', description: '使用页面提供的变量编写标题和正文，避免删除必要的实例与指标信息。' },
          { title: '测试发送', description: '保存后点击“测试发送”，再到通知记录查看 sent 或具体错误。' },
        ],
        notes: ['QQ 邮箱需要先开启 SMTP 并生成授权码；服务端还必须能访问 SMTP 端口。'],
      },
      {
        key: 'channels-bots',
        title: '钉钉 / 飞书 / 企业微信',
        page: 'channels',
        summary: '使用群机器人 Webhook 接收告警消息。',
        steps: [
          { title: '创建群机器人', description: '在对应群聊中添加自定义机器人，设置安全规则并复制 Webhook。' },
          { title: '选择渠道类型', description: '在平台选择钉钉、飞书或企业微信，粘贴对应 Webhook；不要混用不同平台地址。' },
          { title: '配置安全参数', description: '如机器人启用了签名、关键词或 IP 白名单，按平台表单填写并确保模板包含关键词。' },
          { title: '设置等级和模板', description: '选择需要发送的告警等级、触发/恢复开关和消息正文。' },
          { title: '测试并查记录', description: '执行测试发送，群内未收到时查看通知记录中的 HTTP 错误。' },
        ],
      },
      {
        key: 'channels-webhook',
        title: '通用 Webhook',
        page: 'channels',
        summary: '向自建系统发送 JSON 告警消息。',
        steps: [
          { title: '准备接收接口', description: '接口应支持 HTTPS POST、JSON 请求体，并在合理时间内返回 2xx。' },
          { title: '配置地址和认证', description: '填写 Webhook URL，并按接收端要求配置 Token 或请求头。' },
          { title: '设置过滤与模板', description: '选择等级、触发和恢复条件，确保接收端能解析模板字段。' },
          { title: '测试幂等性', description: '测试重复通知时接收端不会产生无法控制的重复工单或操作。' },
        ],
      },
    ],
  },
  {
    key: 'records',
    title: '通知记录',
    page: 'records',
    summary: '核对每次告警通知是否已发送、被跳过或失败，并查看失败原因。',
    steps: [
      { title: '按状态检查', description: 'sent 表示发送成功，failed 表示调用失败，skipped 表示不符合渠道发送规则。' },
      { title: '查看关联信息', description: '核对渠道、告警事件、通知类型、标题、时间和错误消息。' },
      { title: '定位失败原因', description: '认证错误检查密码或 Token，超时检查网络，4xx 检查地址和消息格式。' },
      { title: '重新测试', description: '修正渠道后先执行测试发送，再用测试告警验证真实触发链路。' },
    ],
  },
  {
    key: 'logs',
    title: '日志查询',
    page: 'logs',
    summary: '优先使用图形化简单查询；只有复杂筛选和聚合才需要编写 Loki LogQL。',
    children: [
      {
        key: 'logs-simple',
        title: '简单查询',
        page: 'logs',
        summary: '通过命名空间、应用或 Pod、级别、关键词、时间范围和条数筛选日志。',
        steps: [
          { title: '选择简单模式', description: '命名空间和应用名称可自行输入，不受固定列表限制。' },
          { title: '缩小范围', description: '先选最近 5 或 30 分钟，再填写命名空间和应用/Pod，避免一次查询过多日志。' },
          { title: '选择级别和关键词', description: '级别用于常见 error/warn/info 文本，关键词可查异常类名、请求 ID 或业务提示。' },
          { title: '执行并查看标签', description: '结果按时间展示，同时观察 namespace、pod、container 等标签确认来源。' },
        ],
        notes: ['查询不到日志时，先确认 Loki 已采集该集群、命名空间、Pod 或 Exporter 的日志。'],
      },
      {
        key: 'logs-logql',
        title: '高级 LogQL',
        page: 'logs',
        summary: '直接编写 Loki LogQL，适合组合标签、正则过滤、解析 JSON 和统计。',
        steps: [
          { title: '切换高级模式', description: '从一个明确的标签选择器开始，例如 {namespace="platform"}。' },
          { title: '追加文本过滤', description: '使用 |= "error" 精确包含，或 |~ "error|failed" 正则匹配。' },
          { title: '控制时间和条数', description: '先用较短时间验证语句，再逐步扩大范围。' },
          { title: '处理查询错误', description: '检查引号、花括号、标签名和正则表达式；不要把 SQL 语法写入 LogQL。' },
        ],
        example: '{namespace="platform", app=~"monitor-.*"} |~ "error|failed|exception"',
      },
    ],
  },
  {
    key: 'assistant',
    title: 'AI 助手',
    page: 'assistant',
    summary: '结合选中的监控对象或告警事件进行多轮排查对话，获得原因、验证命令和恢复步骤。',
    steps: [
      { title: '选择上下文', description: '先选择相关监控对象或从告警详情点击“用 AI 分析”，避免只输入模糊问题。' },
      { title: '描述现象', description: '补充发生时间、错误信息、最近变更和影响范围，不要提交密码、Token 或私钥。' },
      { title: '继续追问', description: '围绕建议逐步询问验证命令、预期结果、风险和回滚方式。' },
      { title: '人工验证', description: 'AI 结论仅作为排查建议；在生产执行命令前核对环境、权限和影响。' },
      { title: '回写事件', description: '把已验证的结论和实际处置结果记录到告警事件详情。' },
    ],
  },
  {
    key: 'grafana',
    title: 'Grafana 图表',
    page: 'grafana',
    summary: '查看当前账号监控对象的趋势图；root 账号还可查看平台支撑组件图表。',
    prerequisites: ['目标已成功同步到 Prometheus，并至少完成一次采集。', '平台已正确配置 Grafana API、Prometheus 和 Loki 数据源。'],
    steps: [
      { title: '等待指标采集', description: '新增 Target 后等待一个采集周期，采集状态正常后再创建仪表盘。' },
      { title: '同步 Grafana', description: '进入 Grafana 图表点击同步，平台会匹配或创建该账号的专属仪表盘。' },
      { title: '选择监控对象', description: '从平台提供的 Target 列表进入对应 Node、Nginx、RabbitMQ 等图表。' },
      { title: '调整时间范围', description: '先看最近 15 分钟定位当前异常，再扩大到 6 小时或 24 小时分析趋势。' },
      { title: '处理无数据', description: '检查 Target 采集状态、Prometheus 查询、数据源 UID、仪表盘变量和账号权限。' },
    ],
    notes: ['普通用户只能查看自己的监控数据；root 额外拥有平台 Kubernetes、Prometheus、Loki、Grafana 等支撑组件视图。'],
  },
  {
    key: 'platform-health',
    title: '平台健康（root）',
    page: 'platformHealth',
    rootOnly: true,
    summary: 'root 管理员检查后端依赖和平台支撑服务状态，普通用户不可进入。',
    steps: [
      { title: '查看整体状态', description: 'healthy 表示关键依赖正常，degraded 或 down 需要继续查看组件行。' },
      { title: '检查组件说明', description: '重点关注数据库、Redis、Prometheus、Loki、Grafana 和通知服务的错误信息。' },
      { title: '结合 Kubernetes 排查', description: '检查 platform 与 monitoring 命名空间 Pod、Service、Endpoint 和最近日志。' },
      { title: '恢复后刷新', description: '组件恢复后重新刷新平台健康，确认状态和用户功能均已恢复。' },
    ],
  },
];

export type GuideTreeNode = {
  key: string;
  title: string;
  children?: GuideTreeNode[];
};

export function createGuideTreeData(sections: GuideSection[]): GuideTreeNode[] {
  return sections.map((section) => ({
    key: section.key,
    title: section.title,
    children: section.children?.length ? createGuideTreeData(section.children) : undefined,
  }));
}

export function findGuideSection(key: string, sections: GuideSection[] = guideSections): GuideSection | undefined {
  for (const section of sections) {
    if (section.key === key) return section;
    const child = section.children ? findGuideSection(key, section.children) : undefined;
    if (child) return child;
  }
  return undefined;
}

export function findGuidePath(key: string, sections: GuideSection[] = guideSections, parents: GuideSection[] = []): GuideSection[] {
  for (const section of sections) {
    const path = [...parents, section];
    if (section.key === key) return path;
    const childPath = section.children ? findGuidePath(key, section.children, path) : [];
    if (childPath.length) return childPath;
  }
  return [];
}
