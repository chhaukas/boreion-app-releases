# Produktstatus — sentral Boreion-publisering

## Kontrollert oppsett 2026-10-26

- Sentral scan/publish/tests og separat read-only App-probe er merget til main (PR #1). Ingen database eller annen infrastruktur er opprettet.
- Eksisterende App 5477250 er autentisert med den sentralt lagrede PEM-en på GitHub. Leser godkjent privat kilde og Actions-data; registrert build-only-workflow blir funnet. [Siste integrasjonstest](https://github.com/chhaukas/boreion-app-releases/actions/runs/40308611125) er grønn. Ingen APK er hentet eller eksportert av denne testen, ingen nøkler/private kildenavn er skrevet ut.
- 20 lokale sentrale unit-/negative tester og actionlint bestod. GitHub-CI for den mergete kodeendringen bestod også reell Docker-sandkasse/signaturtest med midlertidig lokal fixture, ingen testrelease.
- Kildeprosjektets metadata/workflow er tilpasset eksisterende sentralmal og merget til privat main. Reell førstekildepolicy med numeriske repo-/workflow-/actor-ID-er og eksisterende deklarert sertifikat er generert/validert privat. productionApproved=false. Signeringsidentiteten må fortsatt bekreftes mot en faktisk ny APK.
- Integrasjonen får HTTP 403 for å lagre policy-secret, opprette environments og beskytte main. Disse ressursene mangler fortsatt. [Kontrollert scan](https://github.com/chhaukas/boreion-app-releases/actions/runs/40308615834) feilet sikkert før App-token/artifact-henting fordi policy mangler. Eksakte eierkommandoer finnes i det private kildeprosjektets SETUP-CENTRAL.md, slik at private kildenavn ikke legges i dette offentlige repoet.
- Kontrollert privat build-only-jobb ble avvist før runnerstart grunnet kontoens betaling/spending limit. Derfor er ekte signert kilde-APK, kryssrepo artifact-nedlasting og full releasekjede fortsatt ikke ende-til-ende-verifisert. Tilgjengelighet av private signeringssecrets er ukjent; ingen nye nøkler genereres.
- Ingen beta-/produksjonsreleases, secret-flytting eller produksjonsgodkjenning er utført. Første reelle produksjons-APK krever fortsatt eierens uttrykkelige godkjenning, policy-aktivering og sentral environment-review.

Neste steg er eierens Settings-/policy-oppsett og avklaring av private Actions-betaling, deretter et privat signert kandidatbygg og separat godkjenning av konkret produksjonsversjon. Nye App-nøkler per kildeprosjekt skal ikke opprettes.
