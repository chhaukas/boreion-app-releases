# boreion-app-releases

# Boreion sentral publisering

Dette er sentralen for `chhaukas/boreion-app-releases`. Den bygges ikke som en server og krever ingen database. GitHub Actions poller godkjente private workflows, henter artifacts via GitHubs REST API og publiserer godkjente, verifiserte APK-er. Portalen fortsetter å lese offentlige releases i eksisterende format.

## Arkitektur og rettigheter

1. Privat Android-repo bygger, tester og signerer på `main`, og laster opp et **privat v4 Actions-artifact**. Det inneholder offentlig kandidat-bundle og en privat proveniensfil. Det har ingen sentral App-nøkkel, ingen callback-token og ingen publiseringsrettighet.
2. `central-scan.yml` kjører cirka hvert 15. minutt på sentralens `main`. En sentral GitHub App med **Actions: read** og automatisk Metadata: read leser bare utvalgte private source-repoer. Kandidater må finnes i lukket policy og være fra vellykket, autorisert workflow_dispatch på riktig branch/workflow-ID/commit.
3. Sentralens eget GITHUB_TOKEN med Actions-write starter `central-publish.yml` i **samme** offentlige repo. workflow_dispatch er et støttet unntak fra GITHUB_TOKENs vanlige blokkering av rekursive workflow-triggere. Run-historikk og eksisterende release-tags undertrykker duplikate forespørsler. Ingen vilkårlig repository_dispatch eller ekstern URL godtas.
4. `plan` sjekker sentral aktør, registrert app, produksjonstillatelse og ekte GitHub-reviewer-/branchbeskyttelse før noen App-nøkkel brukes. Deretter valideres source-repoets numeriske ID/eier, branch, workflow-ID/sti, avsender, rerun-avsender, vellykket status, commit og artifact-binding før godkjenning anmodes.
5. Produksjonskandidaten venter på **publication-production**. Dette er autorisasjon til å hente/verifisere/eksportere private kandidatdata, ikke en erstatning for teknisk kontroll. Godkjenningen skjer før noe APK-artifact legges i offentlig Actions-lagring. Beta kan være automatisk etter eksplisitt sentral kildegodkjenning.
6. `verify` henter de eksakte artifact-bytene med et nytt read-only App-token. GitHubs archive-SHA-256 verifiseres; tokenet tilbakekalles før inspeksjon. ZIP-stier, duplikater, symlinker og størrelser kontrolleres. Privat proveniens må matche API-observasjonene. SDK-verktøy kontrollerer APK-signatur, sertifikat, pakkenavn og faktisk versionName i en pinnet Docker-sandkasse uten nett, root, capabilities, skrivbar root eller monterte credentials. APK-kode kjøres ikke. Bare den sentralt gjennomgåtte pakkeren genererer offentlig bundle. Private proveniensdata og produsentens scripts/notater eksporteres aldri.
7. `publish` er en separat jobb med sentralens **GITHUB_TOKEN Contents-write**, ingen App-PEM, ingen private source-tokens og ingen privat checkout. Den henter bare samme sentrale runs verifiserte artifact, sjekker archive-/APK-hash og format, reserverer tag atomisk, oppretter draft, laster opp og validerer GitHubs asset-digests før draft publiseres. Ingen ubetrodd source-kode eller APK-parser kjøres i denne jobben.

**App-PEM er altså en lesernøkkel, ikke publiseringsnøkkelen.** App-en skal ikke ha Contents-write eller Actions-write noe sted. Repoets automatiske GITHUB_TOKEN publiserer kun i repoet som eier kjøringen. Dermed unngås både sentral App-skrivetilgang til private kilderepoer og kopiering av App-key til nye prosjekter.

## Undersøkte GitHub-begrensninger

Kontotypen `chhaukas` er offentlig bekreftet som **User**, ikke en organisasjon. Betalt abonnement er ikke slått opp eller forutsatt.

- Reusable workflows får secrets fra callerens eksplisitte overføring, ikke automatisk fra repoet som eier workflow-filen. Denne løsningen bruker derfor separate sentrale workflow-kjøringer, ikke skjult secret-arv.
- Et repos GITHUB_TOKEN er begrenset til eget repo. Det kan ikke brukes til å hente private artifacts fra andre repoer. GitHub støtter dette med eksplisitt token med Actions-read, repo, run-ID og artifact-ID. Her brukes REST-mekanismen med eksakt binding og SHA-verifikasjon.
- På GitHub Free kan private repoer bruke repository secrets og Actions innenfor planens kvoter, men private environments krever Pro/Team/Enterprise. Required reviewers er på Free/Pro/Team bare tilgjengelige for offentlige repoer. Review-porten ligger derfor i det **offentlige** sentralrepoet. Ingen private environment-secrets, organisasjonssecrets eller organisasjonsnivå antas.
- Private branch protection kan avhenge av betalt plan. Kildebranchens navn/status og avsender kontrolleres, men vellykket CI alene beviser ikke kodegjennomgang. Gjennomgå den private commiten før produksjonsgodkjenning; aktiver private branchregler der planen tillater det.
- En personlig konto kan ha en privat GitHub App installert bare på utvalgte egne private repoer. Metadata-read er obligatorisk; Actions-read er nødvendig for artifact-API-et. GitHub gir ikke artifact-/workflow-spesifikke App-permissions, så et kompromittert reader-token kan lese andre artifacts i de valgte repoene. Begrens derfor installasjonen og beskytt sentralen.
- Miljøer som bare nevnes i YAML kan opprettes uten protection. Kontrolleren avviser derfor produksjon dersom reviewers, «Protected branches only» eller beskyttet `main` mangler. Sett også «Allow administrators to bypass» av; dersom API-et rapporterer bypass=true avvises kjøringen. Administrator kan fortsatt endre policy/kode; root-eier er en eksplisitt tillitsgrense.
- Prevent self-review gir reell to-person-kontroll, men en eneste operatør kan ikke godkjenne sin egen manuelt startede deployment med dette aktivert. Bruk en ekstra betrodd reviewer dersom uavhengig review kreves. En bevisst tillatt egen godkjenning er fortsatt en manuell beslutning, men skal ikke omtales som uavhengig to-person-kontroll.

Offisielle kilder, undersøkt 26. oktober 2026:

- https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
- https://github.com/actions/download-artifact#download-artifacts-from-other-workflow-runs-or-repositories
- https://docs.github.com/en/rest/actions/artifacts#download-an-artifact
- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

## Engangssteg i sentralrepoet

Disse stegene krever kontoeierens eksplisitte konfigurasjon. Ingen secrets eller produksjonsreleases opprettes av kildekodeleveransen.

1. Gjennomgå og merge sentralens kode til `main` i offentlige `chhaukas/boreion-app-releases`: `.github/workflows/central-{scan,publish}.yml`, `scripts/`, `verifier-image.txt` og prosjektmalene. Beskytt sentral `main`, workflow-/script-filer og policy med PR-/CODEOWNERS-regler og påkrevde kontroller. Ingen source-repoer får skrivetilgang til sentralen. Actions er pinnet til offisielle commit-SHA-er dokumentert i action-lock.json; gjennomgå oppdateringer før produksjonsaktivering. Verifier-containeren er pinnet til faktisk Docker-registry-digest.
2. Gjenbruk den eksisterende private **Boreion App Publisher**, App ID **5477250**. Den har Actions: Read-only og Metadata: Read-only og er installert i den godkjente private kilden. Ikke opprett enda en App. Ved fremtidig onboarding utvides bare denne installasjonens **Only select repositories** med den nye gjennomgåtte kilden. Contents, Administration og andre writes skal fortsatt være av; App-en behøver ikke installeres i distribusjonsrepoet eller portalen.
3. Sett **bare i distribusjonsrepoet** repository variable `BOREION_READER_APP_ID` og repository secret `BOREION_READER_APP_PRIVATE_KEY` (PEM). De brukes av normale workflows som eies av sentralen. Ikke kopier disse til kilderepoer, ikke bruk secrets: inherit, og ikke legg dem i Coolify. Ingen eksisterende produksjonsnøkkel må flyttes automatisk.
4. Sett repository secret `BOREION_SOURCE_POLICY` i **samme sentralrepo**. Start fra policy.example.json og legg til en gjennomgått kilde per offentlig app-ID. Se policy-entry.example.json. 0, REPLACE og tomme lister er bevisst ugyldige plassholdere. Numeriske repo-/eier-/workflow-/actor-ID-er, faktisk Android applicationId og sertifikatets SHA-256 må hentes fra den reelle kilden, ikke gjettes. Policyen er secret fordi sentralrepoet er offentlig og private repo-navn ikke skal ligge i en offentlig allowlist.
5. Opprett `publication-production` i sentralrepoet før workflows aktiveres. Konfigurer **Required reviewers**, «Protected branches only», beskytt faktisk `main`, og slå av administrators bypass. Velg self-review-policy bevisst som beskrevet over. Lag også `publication-beta`, begrens til main og legg gjerne review der også. Uten korrekt production-gate feiler preflight før publisering.
6. Tillat at sentralens workflows bruker Actions-write til egen dispatch og Contents-write kun i publish-jobben. Dette er workflowets automatiske GITHUB_TOKEN; ingen PAT, App-skrivenøkkel eller ekstra publiseringssecret er nødvendig.
7. Start «Discover approved private Android builds» manuelt etter at en kilde har et gyldig bygg. Se at kandidaten blir kontrollert og venter på production-godkjenning. Gjennomgå den private kildecommiten/metadata selv før Approve. Første produksjon krever både `productionApproved: true` i policy etter gjennomgang og GitHub environment-godkjenning. Standardflyten krever review for **hver** produksjonsutgivelse, sterkere enn bare første.

Nyttig ID-oppslag med operatørens eksisterende autentiserte GitHub CLI (ingen secretverdier skal skrives ut):

```sh
gh api user --jq .id
gh api repos/chhaukas/DITT_PRIVATE_REPO --jq '{repositoryId: .id, ownerId: .owner.id}'
gh api repos/chhaukas/DITT_PRIVATE_REPO/actions/workflows/boreion-build.yml --jq '{workflowId: .id, workflowPath: .path}'
```

Policyform (fyll de virkelige ID-ene; ikke kopier plassholder-ID-er til produksjon):

```json
{
  "schemaVersion": 1,
  "centralActorIds": [123],
  "sources": {
    "my-tool": {
      "repository": "chhaukas/DITT_PRIVATE_REPO",
      "repositoryId": 456,
      "ownerId": 123,
      "workflowId": 789,
      "workflowPath": ".github/workflows/boreion-build.yml",
      "branch": "main",
      "actorIds": [123],
      "certificateSha256": "64 lowercase hex-tegn for eksisterende Android-sertifikat",
      "androidPackage": "com.boreion.mytool",
      "productionApproved": false
    }
  }
}
```

Eksemplet over illustrerer feltene og er ikke en gyldig faktisk policy. Den medfølgende tomme policyen aktiverer ingen kilder. GitHub Actions-botens ID er offentlig verifisert som 41898282 og godtas kun for sentrale workflow_dispatch-kjøringer; schedule og manuell rerun må fortsatt komme fra godkjente sentrale aktører.

## Minste oppsett per nytt privat Android-prosjekt

1. Kopier prosjektmalen (`project-template/private-android` i distribusjonsrepoet, eller `templates/private-android` i portalrepoet). V1 bruker workflow_dispatch på main for eksplisitt versjon/kanal; vanlige utviklingspush er ikke offentlige releases. Endre app-ID, metadata og Gradle-/APK-stier. Signer som før med prosjektets **eksisterende** Android-keystore. De fire ANDROID_* repository secrets og ANDROID_SIGNING_CERT_SHA256 kreves fortsatt for selve signeringen; de er ikke sentrale publiseringshemmeligheter og flyttes ikke av denne løsningen. Source-workflowen krever ikke environment på et privat Free-repo.
2. Legg til repoet i Reader App-installasjonens utvalgte repoer og én sentral policyoppføring. Sett sentral productionApproved=false ved første registrering. Dette er den nødvendige sikkerhetsgodkjenningen av ny kilde, ikke kopiering av App-nøkkel eller opprettelse av publisher-token i prosjektet. Ukjente kilder skal ikke selvregistrere.
3. Start source-build og vent på vellykket test/lint/signering og privat artifact. Etterpå er oppdagelse, nedlasting, verifikasjon, versjonsreservasjon og publisering sentral og automatisk, med den påkrevde production-review-porten. Ingen prosjekt-callback eller repo-dispatch-secret trengs. Portalen oppdager den ferdige offentlige releasen som før.

Repoer skal ikke ha BOREION_READER_APP_PRIVATE_KEY, BOREION_DISTRIBUTION_APP_PRIVATE_KEY eller sentrale publiseringstokens. Ved migrering må gamle boreion-distribute.yml-publish-jobber deaktiveres i en gjennomgått kodeendring. Gamle App-installeringer/keys/secrets beholdes urørt til eieren uttrykkelig har godkjent opprydding. Tilbakekall/slett dem først etter kontrollert overgang; ingen automatisk hemmelighetsflytting er implementert.

## Personvern, feil og drift

Sentralen er offentlig. Derfor må **rå private artifacts aldri lastes opp som artifacts i sentralrepoet før godkjenning**, heller ikke bare «for mellomlagring». Her holdes kandidat-ZIP, proof.json og request.json kun på den midlertidige verify-runneren. Først etter export-godkjenning og teknisk kontroll lastes et regenerert, offentlig bundle opp. Kildenavn maskeres i Actions-inputs; offentlige runs viser offentlig app-ID, versjon og et opakt source-run-nummer, ikke privat kildekode eller repo-/commit-lenker. Revieweren må ha egen lesetilgang til den private kilden for meningsfull kodegjennomgang.

Ikke slå på shell tracing eller dump API-svar/runner-miljø i produksjon. Untrusted APK-tool-output fanges og parsers uten å ekkoes til Actions-loggen. Sandkassen monterer kun APK og SDK-verktøy read-only, uten Docker-socket/host-workspace/nøkler. Ingen producer-scripts kjøres sentralt.

App-/version-tags opprettes atomisk. Eksisterende tag, halvferdig draft, dårlig hash eller feil signatur gir feil; ingen force/clobber/automatisk sletting. Bruk normalt en ny versjon etter en mislykket reservasjon, eller la operatør undersøke og eksplisitt rydde en aldri publisert reservasjon. Tidligere produksjonsreleases endres aldri av retry. Katalogformatet `[boreion-app]`/schemaVersion=1, app-ID/tag og SHA-256 er uendret for apps.boreion.com.

Cron er best effort; GitHub kan forsinke kjøringer og slå av schedule etter lang inaktivitet i offentlig repo. Manuell scan og sentral workflow_dispatch er støttet fallback, kun for godkjente brukere. Private artifact-retention er satt til 7 dager og bruker kontoens private Actions-/lagringskvoter. Utløpt artifact må bygges på nytt, ikke omgås. Skanneren ser inntil 1000 vellykkede source-runs fra siste 7 dager per app og 1000 sentrale runs for review-deduplisering. Ved større historikk kan eldre forespørsler trenge manuell gjennomgang; atomiske tags hindrer uansett dobbeltpublisering. En sentral retry er eksplisitt, ikke automatisk omgåelse av avvist review. Én app per private source-repo er støttet i v1.

Kompromittert App-PEM gir bare lesing av Actions-data i utvalgte private repoer, ikke skriving/publisering; dette er fortsatt sensitiv tilgang. Kompromittert sentral hovedbranch/administrator er en root-tillitsgrense og må beskyttes. Gyldig signatur er identitet og integritet, ikke en sikkerhetsrevisjon av appen. Sertifikatrotasjon krever separat gjennomgått plan; ingen nye produksjonsnøkler genereres.

## Verifikasjon før aktivering

[Offentlig GitHub-CI](https://github.com/chhaukas/boreion-app-releases/actions/runs/40304905581) bestod unit-/negative tester og reell Docker-/signaturtest. Koden er også testet lokalt med checksum-verifiserte verktøy. En ekte lokal test-APK signert med en midlertidig testnøkkel ble kontrollert i den faktiske Docker-sandkassen; gyldig signatur ble akseptert, feil cert/package/version og etterfølgende filendring ble avvist. Testnøkkel og APK ble slettet, ingen testrelease ble publisert. Actionlint validerer workflow-syntaksen.

Reell GitHub App-autentisering, valgt privat repo og Actions-read er nå bekreftet (se integrasjonstesten nedenfor). Kryssrepo artifact-nedlasting, GitHub-review-gate og produksjonspublisering er fortsatt ikke ende-til-ende-bekreftet før kontoeieren fullfører policy/beskyttelse og et signert kandidatbygg kan kjøre. Koden installerer eller flytter ingen produksjonshemmeligheter. Test først mot en eksplisitt godkjent ikke-produksjonskilde, uten å publisere test-APK som en reell app.

## Observert kontohindring ved leveranse

GitHub nektet å starte portalrepoets private CI-jobb med meldingen om mislykkede nylige betalinger eller for lav spending limit. Ingen runner/test ble startet der. Lokal portalverifikasjon er grønn, og offentlig sentral-CI kjører separat. Kontoeieren må kontrollere Settings → Billing & plans før private Android-bygg kan forventes å kjøre. Ingen betalingsinnstillinger er endret.

## Kontrollert oppsett etter App-konfigurasjon

Sentralens scan/publish/test-workflows og en separat `central-check-access.yml` ligger nå på main. App-ID 5477250 og den sentralt lagrede PEM-en er faktisk testet på GitHub: [reader-integrasjon](https://github.com/chhaukas/boreion-app-releases/actions/runs/40308611125) bekrefter godkjent privat kilde, eier, Actions-read og registrert build-only-workflow. Testen laster ikke ned eller publiserer APK, og viser ingen private navn eller nøkkelverdier. Den er begrenset til kontoeieren på sentral main.

Kjør samme ufarlige kontroll med numerisk kilde-ID, aldri et privat reponavn i offentlig workflow-input:

```sh
gh workflow run central-check-access.yml --repo chhaukas/boreion-app-releases --ref main -f source_repository_id=NUMERISK_GODKJENT_ID
```

Førstekildens faktiske policy er klargjort privat med produksjon deaktivert. Denne øktens GitHub-integrasjon får 403 for Secrets-write og Administration-write. Sentral policy, environments og main-beskyttelse må derfor settes fra eierens egen autoriserte økt. Private source-bygg er også stoppet før runnerstart av GitHubs betaling/spending limit; det sier ingenting om hvorvidt signeringssecrets er konfigurert. Ingen produksjonsgodkjenning, secret-flytting eller release er utført.

## Én eksplisitt godkjent manuell førstegangsimport

Utgiveren ba særskilt om publisering av sin eksisterende Titan Diagnose 1.1-APK. `import-titan-1-1.yml` er begrenset til denne ene godkjente filens pinnede SHA/blob/sertifikat og dette ene utkastet. Den krever eierens manuelle workflow_dispatch på sentral main, skiller read-only APK-verifikasjon fra Contents-write-jobben og bruker ingen App-PEM. Ingen source-build-proveniens påstås. Dette aktiverer ikke automatiske kilder og omgår ikke fremtidige kilders policy/godkjenninger. Portalen støtter den opprinnelige Android versionName 1.1 uten å relabelere eller endre signert APK.
