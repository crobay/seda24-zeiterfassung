#!/bin/bash
echo "Starting deployment..."
cd /var/www/vhosts/seda.de/app.seda.de/zeiterfassung/frontend
npm run build
rm -rf /var/www/vhosts/seda.de/app.seda.de/httpdocs/assets
cp -r dist/* /var/www/vhosts/seda.de/app.seda.de/httpdocs/
TIMESTAMP=$(date +%s)
sed -i "s/\.js\"/\.js?v=$TIMESTAMP\"/" /var/www/vhosts/seda.de/app.seda.de/httpdocs/index.html
sed -i "s/const CACHE_NAME = .*/const CACHE_NAME = 'seda24-cache-v$TIMESTAMP';/" /var/www/vhosts/seda.de/app.seda.de/httpdocs/service-worker.js
chown -R dsertic:psacln /var/www/vhosts/seda.de/app.seda.de/httpdocs/
echo "Deploy complete with cache-buster: $TIMESTAMP"
echo "PWA/Offline functionality preserved!"
