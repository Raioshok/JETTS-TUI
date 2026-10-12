import { defineFieldCopy } from '@/app/settings/field-copy'

// Português (Brasil) copy for settings field labels and descriptions.
// Mirrors FIELD_LABELS / FIELD_DESCRIPTIONS in app/settings/constants.ts.

export const PT_FIELD_LABELS = defineFieldCopy({
  model: 'Modelo padrão',
  modelContextLength: 'Janela de contexto',
  fallbackProviders: 'Modelos de reserva',
  toolsets: 'Conjuntos de ferramentas ativados',
  timezone: 'Fuso horário',
  display: {
    personality: 'Personalidade',
    showReasoning: 'Blocos de raciocínio'
  },
  desktop: {
    repoScanEnabled: 'Descoberta automática de repositórios',
    repoScanRoots: 'Raízes da descoberta de repositórios',
    repoScanExcludePaths: 'Caminhos de repositório excluídos'
  },
  agent: {
    maxTurns: 'Máximo de passos do agente',
    imageInputMode: 'Anexos de imagem',
    apiMaxRetries: 'Tentativas de API',
    serviceTier: 'Nível de serviço',
    toolUseEnforcement: 'Imposição de uso de ferramentas'
  },
  terminal: {
    cwd: 'Diretório de trabalho',
    backend: 'Backend de execução',
    timeout: 'Tempo limite de comandos',
    persistentShell: 'Shell persistente',
    envPassthrough: 'Repasse de variáveis de ambiente',
    dockerImage: 'Imagem Docker',
    singularityImage: 'Imagem Singularity',
    modalImage: 'Imagem Modal',
    daytonaImage: 'Imagem Daytona'
  },
  fileReadMaxChars: 'Limite de leitura de arquivos',
  toolOutput: {
    maxBytes: 'Limite de saída do terminal',
    maxLines: 'Limite de página de arquivo',
    maxLineLength: 'Limite de tamanho de linha'
  },
  codeExecution: {
    mode: 'Modo de execução de código'
  },
  approvals: {
    mode: 'Modo de aprovação',
    timeout: 'Tempo limite de aprovação',
    mcpReloadConfirm: 'Confirmar recarregamentos de MCP'
  },
  commandAllowlist: 'Lista de comandos permitidos',
  security: {
    redactSecrets: 'Ocultar segredos',
    allowPrivateUrls: 'Permitir URLs privadas'
  },
  browser: {
    allowPrivateUrls: 'URLs privadas no navegador',
    autoLocalForPrivateUrls: 'Navegador local para URLs privadas'
  },
  checkpoints: {
    enabled: 'Checkpoints de arquivos',
    maxSnapshots: 'Limite de checkpoints'
  },
  voice: {
    recordKey: 'Atalho de voz',
    maxRecordingSeconds: 'Duração máxima da gravação',
    autoTts: 'Ler respostas em voz alta'
  },
  stt: {
    enabled: 'Fala para texto',
    echoTranscripts: 'Repetir transcrições',
    provider: 'Provedor de fala para texto',
    local: {
      model: 'Modelo de transcrição local',
      language: 'Idioma da transcrição'
    },
    openai: {
      model: 'Modelo STT da OpenAI'
    },
    groq: {
      model: 'Modelo STT da Groq'
    },
    mistral: {
      model: 'Modelo STT da Mistral'
    },
    elevenlabs: {
      modelId: 'Modelo STT da ElevenLabs',
      languageCode: 'Idioma da ElevenLabs',
      tagAudioEvents: 'Marcar eventos de áudio',
      diarize: 'Separação de falantes'
    }
  },
  tts: {
    provider: 'Provedor de texto para fala',
    edge: {
      voice: 'Voz do Edge'
    },
    openai: {
      model: 'Modelo TTS da OpenAI',
      voice: 'Voz da OpenAI'
    },
    elevenlabs: {
      voiceId: 'Voz da ElevenLabs',
      modelId: 'Modelo da ElevenLabs'
    },
    xai: {
      voiceId: 'Voz da xAI (Grok)',
      language: 'Idioma da xAI',
      speed: 'Velocidade de reprodução da xAI',
      autoSpeechTags: 'Tags de fala automáticas da xAI',
      optimizeStreamingLatency: 'Otimização de latência de streaming da xAI',
      sampleRate: 'Taxa de amostragem da xAI',
      bitRate: 'Taxa de bits da xAI'
    },
    minimax: {
      model: 'Modelo TTS da MiniMax',
      voiceId: 'Voz da MiniMax'
    },
    mistral: {
      model: 'Modelo TTS da Mistral',
      voiceId: 'Voz da Mistral'
    },
    gemini: {
      model: 'Modelo TTS do Gemini',
      voice: 'Voz do Gemini'
    },
    neutts: {
      model: 'Modelo NeuTTS',
      device: 'Dispositivo do NeuTTS'
    },
    kittentts: {
      model: 'Modelo KittenTTS',
      voice: 'Voz do KittenTTS'
    },
    piper: {
      voice: 'Voz do Piper'
    },
    deepinfra: {
      model: 'Modelo TTS da DeepInfra',
      voice: 'Voz da DeepInfra'
    }
  },
  memory: {
    memoryEnabled: 'Memória persistente',
    userProfileEnabled: 'Perfil do usuário',
    memoryCharLimit: 'Orçamento de memória',
    userCharLimit: 'Orçamento do perfil',
    provider: 'Provedor de memória'
  },
  context: {
    engine: 'Mecanismo de contexto'
  },
  compression: {
    enabled: 'Compressão automática',
    threshold: 'Limite de compressão',
    targetRatio: 'Meta de compressão',
    protectLastN: 'Mensagens recentes protegidas'
  },
  delegation: {
    model: 'Modelo dos subagentes',
    provider: 'Provedor dos subagentes',
    maxIterations: 'Limite de turnos dos subagentes',
    maxConcurrentChildren: 'Subagentes em paralelo',
    childTimeoutSeconds: 'Tempo limite dos subagentes',
    reasoningEffort: 'Esforço de raciocínio dos subagentes'
  },
  updates: {
    nonInteractiveLocalChanges: 'Alterações locais na atualização pelo app'
  }
})

export const PT_FIELD_DESCRIPTIONS = defineFieldCopy({
  model: 'Usado em novas conversas, a menos que você escolha outro modelo no compositor.',
  modelContextLength: 'Deixe em 0 para usar a janela de contexto detectada do modelo selecionado.',
  fallbackProviders: 'Entradas provedor:modelo de reserva para tentar se o modelo padrão falhar.',
  display: {
    personality: 'Estilo padrão do assistente em novas sessões.',
    showReasoning: 'Mostrar seções de raciocínio quando o backend as fornecer.'
  },
  desktop: {
    repoScanEnabled: 'Procurar repositórios Git em pastas locais para mostrar em Projetos.',
    repoScanRoots: 'Pastas a examinar. Deixe vazio para examinar sua pasta pessoal.',
    repoScanExcludePaths: 'Pastas (e suas subpastas) a ignorar na descoberta de repositórios.'
  },
  timezone: 'Usado quando o JettsTUI precisa do horário local. Em branco usa o fuso do sistema.',
  agent: {
    imageInputMode: 'Controla como os anexos de imagem são enviados ao modelo.',
    maxTurns: 'Limite de turnos com chamadas de ferramentas antes de o JettsTUI parar uma execução.'
  },
  terminal: {
    cwd: 'Pasta de projeto padrão para o trabalho de ferramentas e terminal.',
    persistentShell: 'Manter o estado do shell entre comandos quando o backend suportar.',
    envPassthrough: 'Variáveis de ambiente repassadas para a execução de ferramentas.',
    dockerImage: 'Imagem de contêiner usada quando o backend de execução é Docker.',
    singularityImage: 'Imagem usada quando o backend de execução é Singularity.',
    modalImage: 'Imagem usada quando o backend de execução é Modal.',
    daytonaImage: 'Imagem usada quando o backend de execução é Daytona.'
  },
  codeExecution: {
    mode: 'Quão estritamente a execução de código fica restrita ao projeto atual.'
  },
  fileReadMaxChars: 'Máximo de caracteres que o JettsTUI pode ler em uma requisição de arquivo.',
  approvals: {
    mode: 'Como o JettsTUI lida com comandos que precisam de aprovação explícita.',
    timeout: 'Quanto tempo os pedidos de aprovação esperam antes de expirar.'
  },
  security: {
    redactSecrets: 'Ocultar segredos detectados do conteúdo visível ao modelo quando possível.'
  },
  checkpoints: {
    enabled: 'Criar snapshots de reversão antes de editar arquivos.'
  },
  memory: {
    memoryEnabled: 'Salvar memórias duradouras que ajudam em sessões futuras.',
    userProfileEnabled: 'Manter um perfil compacto das preferências do usuário.'
  },
  context: {
    engine: 'Estratégia para gerenciar conversas longas perto do limite de contexto.'
  },
  compression: {
    enabled: 'Resumir o contexto mais antigo quando as conversas ficam grandes.'
  },
  voice: {
    autoTts: 'Falar automaticamente as respostas do assistente.'
  },
  tts: {
    xai: {
      voiceId: 'ID de voz da xAI (ex.: eve) ou um ID de voz personalizado.',
      language: 'Código do idioma falado (ex.: en, pt-BR) ou "auto" para detecção automática.',
      speed: 'Velocidade de reprodução. 0.7 = mais lento, 1.0 = normal, 1.5 = mais rápido.',
      autoSpeechTags:
        'Deixar um LLM inserir tags de áudio expressivas ([laughing], [sighs]) no roteiro antes da síntese.',
      optimizeStreamingLatency: 'Equilíbrio entre latência e qualidade. 0 = melhor qualidade, 2 = menor latência.',
      sampleRate: 'Taxa de amostragem do áudio em Hz. Maior = melhor qualidade, arquivos maiores.',
      bitRate: 'Taxa de bits do MP3 em bps. Só se aplica quando o codec é mp3.'
    },
    neutts: {
      device: 'Dispositivo de inferência local do NeuTTS.'
    }
  },
  stt: {
    enabled: 'Ativar transcrição de fala local ou por provedor.',
    echoTranscripts: 'Publicar de volta na conversa a transcrição bruta 🎙️ das mensagens de voz.',
    elevenlabs: {
      languageCode: 'Código de idioma ISO-639-3 opcional. Em branco deixa a ElevenLabs detectar automaticamente.'
    }
  },
  updates: {
    nonInteractiveLocalChanges:
      'Quando o JettsTUI se atualiza pelo app (sem prompt no terminal), manter as edições locais do código (stash) ou descartá-las (discard). Atualizações pelo terminal sempre perguntam.'
  }
})
