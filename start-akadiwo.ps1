

$ErrorActionPreference = 'Stop'

$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
$backend = Join-Path $PSScriptRoot 'contact_api.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Python 3.12 was not found in the expected user install location.'
}
if (-not (Test-Path -LiteralPath $backend -PathType Leaf)) {
    throw 'contact_api.py must be beside this launcher.'
}

$env:AKADIWO_SMTP_HOST = 'smtp.gmail.com'
$env:AKADIWO_SMTP_PORT = '587'
$env:AKADIWO_SMTP_SECURITY = 'starttls'
$env:AKADIWO_FROM_EMAIL = 'akadiwofoundation@gmail.com'
$env:AKADIWO_TO_EMAIL = 'akadiwofoundation@gmail.com'
$env:AKADIWO_SMTP_USER = 'akadiwofoundation@gmail.com'
$env:AKADIWO_BIND = '127.0.0.1'
$env:AKADIWO_PORT = '8765'

if (-not $env:AKADIWO_SMTP_PASSWORD) {
    $securePassword = Read-Host 'Enter the Google App Password (input is hidden)' -AsSecureString
    if ($securePassword.Length -eq 0) {
        throw 'A Google App Password is required to send mail.'
    }
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
        $env:AKADIWO_SMTP_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
}

& $python $backend
