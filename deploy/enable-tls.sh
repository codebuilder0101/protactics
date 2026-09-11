#!/usr/bin/env bash
# ============================================================
#  PROTACTICS — activar HTTPS en siop.co
#
#  Ejecutar UNA VEZ, cuando siop.co y www.siop.co ya resuelvan
#  a 161.97.77.100 (los registros DNS de GoDaddy ya propagados).
#
#      sudo bash /var/www/protactics/deploy/enable-tls.sh
#
#  Qué hace:
#   1. Comprueba que el DNS apunta aquí (si no, aborta: pedir el
#      certificado antes de tiempo gasta cuota de Let's Encrypt).
#   2. Pide el certificado y deja que certbot reescriba el nginx
#      añadiendo el :443 y el redirect 80 -> 443.
#   3. Pone SECURE_COOKIES=true y reinicia la app. Esto va DESPUÉS
#      del certificado a propósito: una cookie Secure sobre HTTP
#      plano no se envía y el login quedaría roto.
# ============================================================
set -euo pipefail

IP_ESPERADA="161.97.77.100"
DOMINIOS=(siop.co www.siop.co)
EMAIL="poorwoman704@gmail.com"

echo "==> 1/3  Comprobando DNS"
for d in "${DOMINIOS[@]}"; do
    resuelto="$(dig +short A "$d" @1.1.1.1 | tail -n1)"
    if [ "$resuelto" != "$IP_ESPERADA" ]; then
        echo "    ERROR: $d resuelve a '${resuelto:-nada}', se esperaba $IP_ESPERADA."
        echo "    El DNS todavía no ha propagado. Espera y vuelve a ejecutar."
        exit 1
    fi
    echo "    OK  $d -> $resuelto"
done

echo "==> 2/3  Solicitando certificado Let's Encrypt"
certbot --nginx \
    -d siop.co -d www.siop.co \
    --redirect \
    --agree-tos --no-eff-email -m "$EMAIL" \
    --non-interactive

echo "==> 3/3  Activando cookies Secure y reiniciando la app"
sed -i 's/^SECURE_COOKIES=false/SECURE_COOKIES=true/' /etc/protactics.env
grep -q '^SECURE_COOKIES=true' /etc/protactics.env \
    || echo 'SECURE_COOKIES=true' >> /etc/protactics.env
nginx -t
systemctl reload nginx
systemctl restart protactics.service

# systemctl marca el servicio «active» en cuanto arranca el proceso (Type=simple),
# no cuando uvicorn ya escucha. Sin esperar al puerto, la comprobación de abajo
# da un 502 falso. Se sondea el puerto hasta 30 s.
echo -n "    esperando a que uvicorn escuche"
for _ in $(seq 30); do
    if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8000/; then
        echo " -> listo"
        break
    fi
    echo -n "."
    sleep 1
done
curl -sf -o /dev/null --max-time 5 http://127.0.0.1:8000/ \
    || { echo; echo "    ERROR: la app no responde"; journalctl -u protactics -n 30 --no-pager; exit 1; }

echo
echo "Listo. Comprobación:"
curl -sI https://siop.co | head -n1
echo "Renovación automática: $(systemctl is-active certbot.timer)"
