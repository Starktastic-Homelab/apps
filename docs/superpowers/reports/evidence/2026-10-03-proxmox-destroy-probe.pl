#!/usr/bin/env perl
# Source-only probe: no Proxmox installation, network, disks or subprocesses.
# Runs the exact pinned destroy_vm function with all external operations mocked.
use strict;
use warnings;
use Digest::SHA qw(sha256_hex);
use Test::More;

my $file = shift or die "usage: perl $0 /path/to/QemuServer.pm\n";
open my $fh, '<', $file or die "$file: $!";
my $source = do { local $/; <$fh> };
is(sha256_hex($source),
   '2752ec819cdf5864b1773fc8c8f0335f9d692248406428f1df055ca60e6e11f5',
   'pinned qemu-server a7b4240 source') or BAIL_OUT('source mismatch');
my ($function) = $source =~ /(^sub destroy_vm \{.*?^\})/ms;
die "destroy_vm extraction failed" unless $function;

our ($conf, @freed, @destroyed, %owners);
sub drive_is_cdrom { return $_[0]->{cdrom} // 0; }
sub log_warn { die "unexpected upstream warning: @_"; }

{
    package PVE::QemuConfig;
    sub cleanup_fleecing_images {}
    sub load_config { return $main::conf; }
    sub has_lock { return 0; }
    sub check_lock {}
    sub foreach_volume_full {
        my ($class, $cfg, $opts, $callback) = @_;
        for my $slot (sort keys %{ $cfg // {} }) {
            next unless $slot =~ /^(?:scsi|virtio|unused)\d+$/;
            $callback->($slot, $cfg->{$slot});
        }
    }
    sub destroy_config { push @main::destroyed, $_[1]; }
}
{
    package PVE::Storage;
    sub path {
        my ($cfg, $volume) = @_;
        die "unmocked volume $volume" unless exists $main::owners{$volume};
        return ("/mock/$volume", $main::owners{$volume});
    }
    sub vdisk_free { push @main::freed, $_[1]; }
}
{
    package PVE::QemuServer::Network;
    sub delete_ifaces_ipams_ips {}
}
eval $function;
die $@ if $@;

%owners = (
    'nas:201/vm-201-disk-0.raw' => 201,
    'nas:9999/vm-9999-pvc-example.raw' => 9999,
);
for my $placement ('scsi1', 'unused0', 'pending') {
    @freed = (); @destroyed = ();
    $conf = { virtio0 => { file => 'nas:201/vm-201-disk-0.raw' }, snapshots => {} };
    my $disk = { file => 'nas:9999/vm-9999-pvc-example.raw' };
    if ($placement eq 'pending') { $conf->{pending} = { scsi1 => $disk }; }
    else { $conf->{$placement} = $disk; }
    destroy_vm({}, 201, 0, undef, 0);
    is_deeply(\@freed, ['nas:201/vm-201-disk-0.raw'],
        "worker deletion skips foreign-owned CSI image in $placement");
    is_deeply(\@destroyed, [201], 'worker config is removed');
}

@freed = (); @destroyed = ();
$conf = { scsi1 => { file => 'nas:9999/vm-9999-pvc-example.raw' }, snapshots => {} };
destroy_vm({}, 9999, 0, undef, 0);
is_deeply(\@freed, ['nas:9999/vm-9999-pvc-example.raw'],
    'negative control: deletion of the owning VM removes its image');
done_testing();
