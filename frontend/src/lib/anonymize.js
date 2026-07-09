/**
 * Helper de anonimizacao de PII no frontend (Monitoria).
 * NEW (08/07/2026 - B3): aplicar para usuarios que NAO sao admin/super-admin.
 *
 * Regra: admin/super-admin veem dados completos (auditoria). Demais users
 * veem dados mascarados (LGPD Art. 12 - minimizacao).
 */

/**
 * Mascara filename: "JoaoSilva_2025-01-01.mp3" -> "J**********a_****-**-**.mp3"
 * Mantem extensao visivel.
 */
export function anonymizeFilename(filename) {
  if (!filename) return ''
  const lastDot = filename.lastIndexOf('.')
  if (lastDot < 0) return '***'
  const name = filename.substring(0, lastDot)
  const ext = filename.substring(lastDot)
  if (name.length <= 2) return `**${ext}`
  // Mantem primeira letra + ultima letra + ***
  const first = name[0]
  const last = name[name.length - 1]
  const middle = '*'.repeat(Math.max(name.length - 2, 3))
  return `${first}${middle}${last}${ext}`
}

/**
 * Mascara transcricao: CPF, RG, telefone, email.
 * Reusa os mesmos patterns do backend/core/lgpd.py.
 */
const PII_PATTERNS = [
  // Email
  [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, '[EMAIL]'],
  // CPF
  [/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/g, '[CPF]'],
  [/\b\d{11}\b/g, '[CPF]'],
  // Telefone
  [/\(\d{2}\)\s*9?\d{4}-?\d{4}\b/g, '[PHONE]'],
  [/\b\d{2}\s*9\d{4}-?\d{4}\b/g, '[PHONE]'],
  [/\b9\d{4}-?\d{4}\b/g, '[PHONE]'],
  // RG
  [/\b\d{2}\.\d{3}\.\d{3}-?[0-9X]\b/g, '[RG]'],
  // Cartao
  [/\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/g, '[CARD]'],
]

export function anonymizeTranscript(text) {
  if (!text) return text
  let result = text
  for (const [pattern, replacement] of PII_PATTERNS) {
    result = result.replace(pattern, replacement)
  }
  return result
}

/**
 * Verifica se user pode ver dados completos (admin ou super-admin).
 */
export function canSeeFullData(userRole) {
  if (!userRole) return false
  // Portal retorna 'super-admin', 'admin', 'analyst', 'atendente', 'user'
  // Apenas super-admin e admin veem dados completos
  return ['super-admin', 'admin'].includes(userRole)
}