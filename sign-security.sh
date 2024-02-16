# This script must be run in the directory of the repo
if [[ -f "security.txt" ]]; then
    TODAY=$(date +%Y-%m-%d)
    EXPIRE=$(date +%Y-%m-%dT00:00:00.000Z -d "$TODAY + 6 month")
    cp security.txt temp-security.txt
    echo "Expires: $EXPIRE" >> temp-security.txt
    gpg --clearsign --default-key psirt@linaro.org --passphrase Radial-swipe-Division-Fault-2Accustom-Jaw6-4duration-potato temp-security.txt
    rm temp-security.txt
    mv temp-security.txt.asc security.txt.asc
fi
