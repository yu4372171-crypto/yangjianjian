param([Parameter(Mandatory=$true)][string]$JobFile)
$ErrorActionPreference='Stop'
$taskJob=Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
$taskInstall=[IO.Path]::GetFullPath($taskJob.installDir).TrimEnd('\')
$taskPackage=[IO.Path]::GetFullPath($taskJob.package)
$taskCache=Join-Path $taskInstall 'Backend\runtime\app_updates'
if(-not $taskPackage.StartsWith($taskCache+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Update package outside cache'}
if(-not ([IO.Path]::GetFullPath($taskJob.resultPath)).StartsWith($taskCache+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Invalid result path'}
$taskExes=@($taskJob.exes | ForEach-Object {[IO.Path]::GetFullPath([string]$_)})
if($taskExes.Count -lt 1){throw 'No application executable recorded'}
$taskResult=@{status='failed';version=$taskJob.version;message=''}
$taskStopped=$false
$taskRestart=@{status='pending';message=''}
try{
  Set-Content -LiteralPath ([IO.Path]::ChangeExtension($JobFile,'.started')) -Value 'ready' -Encoding ASCII
  $taskDeadline=[DateTime]::UtcNow.AddMinutes(3)
  do {
    $taskRunning=@(Get-CimInstance Win32_Process | Where-Object {$_.ExecutablePath -in $taskExes})
    if($taskRunning.Count -eq 0){$taskStopped=$true;break}
    Start-Sleep -Milliseconds 500
  }while([DateTime]::UtcNow -lt $taskDeadline)
  if(-not $taskStopped){throw 'Application is still open. Close other app windows and try again.'}
  if((Get-Item -LiteralPath $taskPackage).Length -ne $taskJob.size){throw 'Update size mismatch'}
  if((Get-FileHash -LiteralPath $taskPackage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskJob.sha256){throw 'Update checksum mismatch'}
  $taskSetup=Start-Process -FilePath $taskPackage -ArgumentList ('/S /D='+$taskInstall) -WindowStyle Hidden -PassThru
  $taskSetup.WaitForExit()
  if($taskSetup.ExitCode -ne 0){throw ('Installer exit code '+$taskSetup.ExitCode)}
  $taskVersion=Get-Content -LiteralPath (Join-Path $taskInstall 'app-version.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  if($taskVersion.version -ne $taskJob.version){throw 'Installed version does not match release'}
  $taskResult.status='installed'
  $taskResult.message='Update installed successfully'
  $taskRestart.status='restarting'
  $taskRestart.message='Application restart is starting'
}catch{
  $taskResult.message=$_.Exception.Message
}finally{
  if($taskStopped -and (Test-Path -LiteralPath $taskExes[0])){
    try{
      $taskProcess=Start-Process -FilePath $taskExes[0] -WorkingDirectory $taskInstall -PassThru
      if(-not $taskProcess.HasExited){
        $taskRestart.status='started'
        $taskRestart.message='Application restart process started'
      }else{
        $taskRestart.status='failed'
        $taskRestart.message=('Application exited during restart with code '+$taskProcess.ExitCode)
      }
    }catch{
      $taskRestart.status='failed'
      $taskRestart.message=$_.Exception.Message
    }
  }elseif($taskStopped){
    $taskRestart.status='failed'
    $taskRestart.message='Installed application executable was not found'
  }else{
    $taskRestart.status='not_required'
    $taskRestart.message='Application was not closed before installation'
  }
  $taskResult.restart=$taskRestart
  $taskResult | ConvertTo-Json | Set-Content -LiteralPath $taskJob.resultPath -Encoding UTF8
}
