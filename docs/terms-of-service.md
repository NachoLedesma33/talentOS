# Términos y condiciones de TalentOS

Estado: demo/local. Estos términos describen las reglas de uso del repositorio y de la instancia de demostración. No constituyen asesoría legal ni autorizan el tratamiento de datos personales reales.

## 1. Uso permitido

TalentOS permite gestionar vacantes, candidatos sintéticos, documentos privados, evaluaciones con evidencia, workflows asistidos y automatizaciones con aprobación humana. El uso se limita a las organizaciones y cuentas autorizadas por el administrador del despliegue.

## 2. Cuentas y organizaciones

- Cada persona usa su propia cuenta; no se comparten credenciales.
- Los roles y permisos se asignan dentro de la organización y se verifican en servidor.
- El administrador puede retirar accesos y cambiar roles; las acciones quedan registradas.
- Los identificadores públicos son UUID; no se exponen correlativos de usuarios.

## 3. Contenido del usuario

Quien introduce vacantes, candidatos o documentos es responsable de su veracidad, procedencia y autorización para tratarlos. En demo solo se permiten datos sintéticos. Está prohibido subir CV reales, secretos, credenciales, malware o contenido que infrinja derechos de terceros.

La plataforma valida extensión, MIME, firma real, tamaño y número de páginas de los archivos. El contenido se almacena en storage privado bajo clave UUID y las URLs de descarga caducan.

## 4. Uso prohibido

- Intentar acceder a otra organización o eludir roles y permisos.
- Automatizar peticiones sin límite o explotar endpoints sensibles.
- Inyectar instrucciones en CV o campos para manipular salidas de IA.
- Extraer modelos, secretos, logs o datos de otros tenants.
- Publicar credenciales, tokens ni datos personales reales en issues, docs o capturas.
- Usar la IA para decidir contrataciones automáticas o inferir atributos protegidos.

## 5. Asistencia de IA y aprobación humana

Los agentes proponen extracciones, evaluaciones y acciones. No ejecutan SQL libre, shell, acceso arbitrario a archivos ni efectos externos sin aprobación. Las salidas se validan con contratos y deben mostrar criterios, evidencia y limitaciones. Toda acción sensible requiere una decisión humana explícita.

## 6. Integraciones externas

Las integraciones remotas son opcionales. En demo funciona el proveedor `mock`; no se requieren credenciales pagadas. Si se activa un proveedor externo, la organización debe configurar secretos fuera del repositorio y aceptar sus condiciones propias. Los correos salientes requieren aprobación adicional.

## 7. Disponibilidad y cambios

El despliegue local puede interrumpirse para migraciones, pruebas o reconstrucción del entorno. Las funcionalidades pueden cambiar entre fases del roadmap; los cambios de contrato se documentan antes de modificarse. No se promete latencia de inferencia local sin medición.

## 8. Propiedad intelectual

El código, los SVG originales y la documentación de TalentOS pertenecen al proyecto. Los derechos sobre datos y documentos introducidos permanecen en quien los aporta, sin perjuicio de las responsabilidades de la sección 3.

## 9. Incumplimiento

El administrador puede suspender cuentas, revocar sesiones, retirar permisos o eliminar contenido sintético cuando detecte uso prohibido. Las acciones sensibles se registran con actor y timestamp.

## 10. Límites

TalentOS no sustituye la revisión humana, no garantiza exactitud de extractores o modelos y no ofrece asesoría legal, laboral ni de cumplimiento. Los riesgos abiertos se listan en `docs/security-review.md`; antes de usar datos reales deben cerrarse o aceptarse por escrito.

## 11. Privacidad

El tratamiento de datos se describe en `docs/privacy-policy.md`. La política y estos términos se actualizan en el repositorio con cada lote que cambie su contenido.
