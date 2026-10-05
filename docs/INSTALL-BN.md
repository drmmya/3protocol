# Ubuntu 24.04-এ ইনস্টল

এই release-এর local code tests হয়েছে; বাস্তব VPS-এ VPN connection, Internet routing এবং SSL এখনও পরীক্ষা করতে হবে।

1. Fresh Ubuntu 24.04 VPS ব্যবহার করুন। Root access, systemd ও TUN থাকতে হবে।
2. ZIP extract করুন। `vpn-panel` folder-এর ভিতরের সব file/folder GitHub repository root-এ upload করুন; সেখানে `install.sh` থাকবে।
3. যেমন repository `https://github.com/drmmya/test` হলে PuTTY-তে root হিসেবে চালান:

```bash
sudo apt update && sudo apt install -y git curl python3 && git clone https://github.com/drmmya/test /root/vpn-panel-final && cd /root/vpn-panel-final && sudo bash install.sh
```

নিজের repository URL ব্যবহার করুন। `/root/vpn-panel-final` আগে থেকে থাকলে update command:

```bash
cd /root/vpn-panel-final && git pull --ff-only && sudo bash install.sh
```

প্রথম install-এ শুধু Admin password চাইবে (৮–২৫৬ character)। Username `Admin`। কোনো protocol-এ default user তৈরি হবে না; panel-এর Users থেকে নিজে add করুন। পুনরায় install করলে existing users/password থাকবে। Private launcher দরকার নেই। Panel: `https://VPS-IP:9443`। প্রথমে self-signed certificate warning আসবে—installer-এর fingerprint মিলিয়ে trust করুন।

Provider firewall-এ TCP 80/443/8443/4443/9443 এবং UDP 1194/8443/4443 খুলুন। SSH port আগের মতো রাখুন।

Users → Config থেকে OpenVPN profile, OpenConnect details বা VMess link নিন। V2Ray-এর জন্য app-এ VMess/TCP-compatible importer লাগবে। TCP 4443-এ VMess/TCP এবং UDP 4443-এ VMess/mKCP আছে। UDP-এর জন্য আলাদা profile নিন। Server legacy default framing ব্যবহার করে; modern Xray client-এ matching FinalMask-সহ complete JSON export ব্যবহার করুন। শুধু KCP link import হলেই সব app-এ connection কাজ করবে ধরে নেবেন না।

Domain পরে দিতে পারবেন: DNS A record VPS-এ point করুন → Domain & SSL → hostname/email দিয়ে SSL install করুন। Panel তখনও 9443 port-এ থাকবে।

OpenVPN session speed ও OpenConnect user speed আছে; V2Ray per-device speed control নেই। Shared profile থেকে exact physical device সংখ্যা জানা যায় না। OpenConnect-এর IPv6 আপনার app-এ block/handle করতে হবে।

কোনো install error হলে `/var/log/vpn-panel-install.log` নিন। আগে internal/private test করুন; routing verify না করে production-ready ধরে নেবেন না।
