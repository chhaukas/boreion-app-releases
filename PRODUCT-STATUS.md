# Produktstatus — sentral Boreion-publisering

## Eiergodkjent manuell Titan-import

Utgiveren har nå uttrykkelig bedt om publisering av vedlagte Titan-Diagnose-1.1.apk. Den faktiske, uendrede filen har Android versionName 1.1, versionCode 2, pakkenavn no.titan.diagnose, minimum API22 og korrekt eksisterende signeringssertifikat. SHA-256 er 43d5af830e95d3d0776ab9eed7c96b33dc310ea1fce5819f7552e85bd8c9489b (25223 bytes). Dette er en manuell godkjent import, ikke et nytt source-build eller en oppdiktet workflow-attestasjon.

Draft 424163700/tag chhaukas-android-tredemolle/v1.1 er opprettet. Opplasting fra Codex til uploads.github.com ble avvist med 401, selv om REST/Git-data fungerer. Den eksplisitte engangsworkflowen import-titan-1-1.yml bruker derfor ekte sentralt GITHUB_TOKEN på GitHub-runneren. Bare eieren på main kan starte den, og kun nøyaktig pinnede APK-/metadata-bytes godtas. Read-only verifier kontrollerer hash/signatur/pakke/faktisk versjon i Docker-sandkasse før en separat writer-jobb henter samme runs digest-bundne bundle, verifiserer GitHub-asset-digests og publiserer bare dette ene tomme utkastet. Ingen App-PEM eller APK-parser finnes i writer-jobben. Ingen automatisk overskriving.

Den automatiske source-policyen for fremtidige bygg forblir deaktivert og får ingen produksjonsgodkjenning fra denne enkeltfil-importen. Innstilling-/betalingshindrene i historikken gjelder fortsatt den automatiske flyten. Publiseringsresultat føres etter faktisk kjøring.

## Kontrollert oppsett 2026-10-26

- Sentral scan/publish/tests og separat read-only App-probe er merget til main (PR #1). Ingen database eller annen infrastruktur er opprettet.
- Eksisterende App 5477250 er autentisert med den sentralt lagrede PEM-en på GitHub. Leser godkjent privat kilde og Actions-data; registrert build-only-workflow blir funnet. [Siste integrasjonstest](https://github.com/chhaukas/boreion-app-releases/actions/runs/40308611125) er grønn. Ingen APK er hentet eller eksportert av denne testen, ingen nøkler/private kildenavn er skrevet ut.
- 20 lokale sentrale unit-/negative tester og actionlint bestod. GitHub-CI for den mergete kodeendringen bestod også reell Docker-sandkasse/signaturtest med midlertidig lokal fixture, ingen testrelease.
- Kildeprosjektets metadata/workflow er tilpasset eksisterende sentralmal og merget til privat main. Reell førstekildepolicy med numeriske repo-/workflow-/actor-ID-er og eksisterende deklarert sertifikat er generert/validert privat. productionApproved=false. Signeringsidentiteten må fortsatt bekreftes mot en faktisk ny APK.
- Integrasjonen får HTTP 403 for å lagre policy-secret, opprette environments og beskytte main. Disse ressursene mangler fortsatt. [Kontrollert scan](https://github.com/chhaukas/boreion-app-releases/actions/runs/40308615834) feilet sikkert før App-token/artifact-henting fordi policy mangler. Eksakte eierkommandoer finnes i det private kildeprosjektets SETUP-CENTRAL.md, slik at private kildenavn ikke legges i dette offentlige repoet.
- Kontrollert privat build-only-jobb ble avvist før runnerstart grunnet kontoens betaling/spending limit. Derfor er ekte signert kilde-APK, kryssrepo artifact-nedlasting og full releasekjede fortsatt ikke ende-til-ende-verifisert. Tilgjengelighet av private signeringssecrets er ukjent; ingen nye nøkler genereres.
- Ingen beta-/produksjonsreleases, secret-flytting eller produksjonsgodkjenning er utført. Første reelle produksjons-APK krever fortsatt eierens uttrykkelige godkjenning, policy-aktivering og sentral environment-review.

Neste steg er eierens Settings-/policy-oppsett og avklaring av private Actions-betaling, deretter et privat signert kandidatbygg og separat godkjenning av konkret produksjonsversjon. Nye App-nøkler per kildeprosjekt skal ikke opprettes.
