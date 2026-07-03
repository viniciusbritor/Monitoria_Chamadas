# Permissao `monitoria-queue-manager` (a criar no Firestore)

## Quando criar
- Apos deploy do modulo Queue Manager em producao
- Permite usuarios NAO-super-admin gerenciarem a fila (ex: SRE/Operador senior)

## Como criar
1. Acessar Firebase Console: https://console.firebase.google.com/project/coherence-ominichannel-fs/firestore
2. Navegar para `user_permissions` collection
3. Para cada usuario autorizado (ex: `sre@coherence.ai`):
   - Document ID: `<email_do_usuario>`
   - Campo `monitoria-queue-manager`: `true`
   - Campo `is_active`: `true`
   - Campo `approved_at`: timestamp atual

## Comportamento atual (ate criar)
- O endpoint usa `require_admin_user` que checa **apenas** `is_super_admin`
- Apenas `viniciusbritor@gmail.com` (e outros super-admins) tem acesso
- Este arquivo documenta a intencao para evolucao futura

## Esquema Firestore esperado
```
user_permissions/
  viniciusbritor@gmail.com/  (super_admin ja passa pelo require_admin_user)
    monitoria-chamadas: { is_active: true, is_approved: true }
    monitoria-queue-manager: { is_active: true, is_approved: true }
  sre@coherence.ai/  (futuro)
    monitoria-queue-manager: { is_active: true, is_approved: true, approved_at: <ts> }
```

## Proxima evolucao
Quando multiplos usuarios precisarem acessar o Queue Manager sem ser super-admin:
1. Modificar `require_admin_user` para aceitar `is_super_admin OR has_module_perm`
2. Adicionar parametro `module_id="monitoria-queue-manager"` ao dependency
3. Atualizar o helper em `core/portal_auth.py` para usar `is_authorized_for_module`
