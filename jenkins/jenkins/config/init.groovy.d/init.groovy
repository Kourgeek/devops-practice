import jenkins.model.*
import hudson.security.*
import hudson.tasks.Mailer

def instance = Jenkins.getInstance()

// ============================================================
// Настройка безопасности: HudsonPrivateSecurityRealm
// ============================================================
def hudsonRealm = new HudsonPrivateSecurityRealm(false)
hudsonRealm.createAccount("admin", "admin123")
instance.setSecurityRealm(hudsonRealm)

// ============================================================
// Полные права для авторизованных пользователей
// ============================================================
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
instance.setAuthorizationStrategy(strategy)

// ============================================================
// Отключение CSRF-протектора (для CI/CD CLI-интеграций)
// ============================================================
def crumbIssuer = new hudson.security.csrf.DefaultCrumbIssuer()
instance.setCrumbIssuer(crumbIssuer)

// ============================================================
// Настройка Mailer (опционально, для уведомлений)
// ============================================================
def mailer = instance.getExtensionList(hudson.tasks.Mailer.UserProperty::class)[0]
// mailer.setSite("smtp.example.com")
// mailer.setSmtpAuthUser("user")
// mailer.setSmtpAuthPassword("pass")

// ============================================================
// Отключаем setup wizard (чтобы не мешал при повторных запусках)
// ============================================================
System.setProperty("jenkins.install.runSetupWizard", "false")

instance.save()

println "============================================="
println "Jenkins configured successfully"
println "  User: admin"
println "  Password: admin123"
println "  Authorization: FullControlOnceLoggedIn"
println "  CSRF: Enabled (DefaultCrumbIssuer)"
println "============================================="
