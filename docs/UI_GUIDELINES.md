# Coherence AI - UI Guidelines

Esta documentação define a identidade visual oficial da Coherence para a plataforma Monitoria CX. A plataforma adota a estética **Clean Light** com efeito Glassmorphism em todo o sistema.

## 1. Tela de Login (Clean Light Premium)
A página de entrada segue uma estética clara e minimalista:
- **Background**: `#f9fafb` (Fundo claro/off-white) com elementos sutis de desfoque decorativos em tom azulado para profundidade.
- **Logotipo**: Logotipo principal `/logo.png` centralizado acima do cartão, com fallback seguro para `/logo-top.png` caso o arquivo principal não carregue. Deve ser alinhado horizontalmente com o subtexto (`flex items-center gap-3`) com divisor vertical de `1px` (`bg-black/10`) e altura ajustada para `h-10` para emparelhar com as letras do painel.
- **Cartão de Login**: Fundo branco translúcido usando `glass-panel` (`bg-white/70 backdrop-blur-xl border border-black/5 shadow-2xl`).
- **Google Login**: Padrão Google integrado ao design claro.

## 2. Dashboard Interno e Cabeçalho (Clean Light Glassmorphism)
A interface interna segue uma paleta clara para garantir legibilidade durante o uso operacional diário:
- **Cabeçalho (Header)**: O logotipo `/logo-top.png` deve ser alinhado horizontalmente (`flex items-center gap-3`) com o texto "MONITORIA DE | CHAMADA" usando uma altura de `h-9` ou `h-10` no Tailwind e um divisor vertical central de `1px` (`bg-black/10`). Isso garante que a logo e a tipografia do painel fiquem perfeitamente proporcionais e alinhadas.
- **Background**: `#f9fafb` (Fundo geral claro)
- **Surface**: `#ffffff` (Cartões e modais brancos)
- **Primary**: `#3b82f6` (Azul corporativo principal para botões e destaques)
- **Text Main**: `#171717` (Preto/Cinza escuro para legibilidade máxima)
- **Text Muted**: `#525252` (Cinza para textos de suporte)

Os componentes do dashboard utilizam o efeito `glass-panel`:
- Fundo branco levemente translúcido (`rgba(255,255,255,0.7)`)
- Desfoque (backdrop-filter: `blur(12px)`)
- Bordas muito sutis (preto 5% de opacidade)
- Sombras elegantes projetadas no fundo claro.

## Tipografia Geral
- Fonte padrão de sistema (System Sans) / Inter
- Títulos fortes e de peso (`font-bold`)
- Textos limpos e responsivos

**Nota para Agentes IA:** É proibido alterar estas cores ou esta estética sem a permissão expressa do usuário.

