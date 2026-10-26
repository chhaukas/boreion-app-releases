# Privat Android-prosjekt: bygg og signer, uten publiseringsnøkkel

Kopier `.github/workflows/boreion-build.yml`, `scripts/prepare-release.py` og `boreion-app.json` til prosjektet. Tilpass unik app-ID, Android-pakkenavn, navn, metadata og Gradle-/APK-stier. Sett public=true bare for en godkjent offentlig app.

Prosjektet bruker **kun eksisterende Android-signering**: ANDROID_KEYSTORE_BASE64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD som repository secrets og ANDROID_SIGNING_CERT_SHA256 som repository variable. Ikke kopier noen sentral GitHub App-PEM eller publiseringstoken til dette repoet. En environment i et privat repo forutsettes ikke.

Workflow_dispatch på main bygger, tester, linter og signerer, kontrollerer sertifikat/versionName og laster opp et privat, navngitt v4-artifact med request.json. Det eksporterer ingen sentrale credentials og gjør ingen release/API-write i distribusjonsrepoet. Etterpå henter den sentrale publiseringstjenesten godkjente artifacts automatisk, og sentral production-review beholdes.

Nytt prosjekt krever én kildegodkjenning i sentral policy og at repoet legges til i Reader App-installasjonen. Ingen ny App-key eller callback-secret opprettes i prosjektet. Full veiledning og GitHub Personal/Free-begrensninger finnes i sentralens README (`templates/central-publisher/README.md` i portalrepoet eller roten av distribusjonsrepoet).

Ved migrering erstattes gamle boreion-distribute.yml og dens publish-jobb med denne build-only-workflowen. Ikke flytt/slett gamle produksjonshemmeligheter uten eierens eksplisitte godkjenning og kontrollert overgang. Ingen test-APK skal publiseres som ekte app.
