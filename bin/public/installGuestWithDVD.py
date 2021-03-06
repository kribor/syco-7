#!/usr/bin/env python
'''
Install a KVM guest from DVD instead of cobbler.

This will probably only be used to install the installation server that hosts
the cobbler service.

This script should be executed directly on a kvm host.

All configurations are retrived from the install.cfg.

'''

__author__ = "daniel.lindh@cybercow.se"
__copyright__ = "Copyright 2011, The System Console project"
__maintainer__ = "Daniel Lindh"
__email__ = "syco@cybercow.se"
__credits__ = ["???"]
__license__ = "???"
__version__ = "1.0.0"
__status__ = "Production"

import os
import time

import app
import config
from general import set_config_property_batch, x
import net
import nfs
import sys
import disk


def build_commands(commands):
    commands.add(
        "install-guest", install_guest, "hostname",
        help="Install KVM guest from dvd.")


class install_guest:
    hostname = None

    def __init__(self, args):
        self.check_commandline_args(args)
        app.print_verbose("Install kvm guest " + self.hostname + ".")
        self.check_if_host_is_installed()
        self.init_host_options_from_config()

        self.mount_dvd()
        self.create_kickstart()
        self.start_nfs_export()

        self.create_kvm_host()

        self.stop_nfs_export()
        self.unmount_dvd()

    def check_commandline_args(self, args):
        if len(args) != 2:
            raise Exception("Enter the hostname of the server to install")
        else:
            self.hostname = args[1]

    def check_if_host_is_installed(self):
        result = x("virsh list --all")
        if self.hostname in result:
            raise Exception(self.hostname + " already installed")

    def init_host_options_from_config(self):
        """
        Initialize all used options from install.cfg.

        If the options are invalid, app and config will throw exceptions,
        that will be forwarded to the starter app.

        """
        # The ip connected to the admin net, from which the nfs
        # export is done.
        self.kvm_host_ip = net.get_lan_ip()

        self.ram = str(config.host(self.hostname).get_ram())
        self.cpu = str(config.host(self.hostname).get_cpu())
        self.cpu_max = str(config.host(self.hostname).get_cpu_max())

        self.set_kickstart_options()

    def set_kickstart_options(self):
        '''
        Properties that will be used to replace ${XXX} vars in kickstart file.

        '''
        prop = {}
        prop['\$hostname'] = self.hostname

        if config.general.is_back_enabled():

            back_line = \
                "network --bootproto=static --ip=" + \
                config.host(self.hostname).get_back_ip() + \
                " --netmask=" + \
                config.general.get_back_netmask() + \
                " --hostname=" + \
                self.hostname + \
                " --device=eth0 --onboot=on --noipv6"

            #Resolver and gateway optional on back net
            if config.general.get_back_resolver_ip() is not None:
                back_line += " --nameserver=" + \
                    config.general.get_back_resolver_ip()

            if config.general.get_back_gateway_ip() is not None:
                back_line += " --gateway=" + \
                    config.general.get_back_gateway_ip()

            front_if = "eth1"
        else:
            back_line = ""
            front_if = "eth0"

        front_line = \
            "network --bootproto=static --ip=" + \
            config.host(self.hostname).get_front_ip() + \
            " --netmask=" + \
            config.general.get_front_netmask() + \
            " --gateway=" + \
            config.general.get_front_gateway_ip() + \
            " --hostname=" + \
            self.hostname + \
            " --device=" + \
            front_if + \
            " --onboot=on --nameserver=" + \
            config.general.get_front_resolver_ip() + \
            " --noipv6"

        prop['\$backnet_kickstart_line'] = back_line
        prop['\$frontnet_kickstart_line'] = front_line

        prop['\$default_password_crypted'] = app.get_root_password_hash()

        prop['\$disk_swap_mb'] = config.host(self.hostname).get_disk_swap_mb()
        prop['\$disk_var_mb'] = config.host(self.hostname).get_disk_var_mb()
        prop['\$disk_log_mb'] = config.host(self.hostname).get_disk_log_mb()
        prop['\$total_disk_mb'] = config.host(self.hostname).get_total_disk_mb()
        prop['\$total_disk_gb'] = config.host(self.hostname).get_total_disk_gb()
        prop['\$boot_device'] = config.host(self.hostname).get_boot_device("vda")
        prop['\$vol_group'] = config.host(self.hostname).get_vol_group()

        self.property_list = prop

    @staticmethod
    def mount_dvd():
        if not os.access("/media/dvd", os.F_OK):
            x("mkdir /media/dvd")

        if not os.path.ismount("/media/dvd"):
            x("mount -o ro -t iso9660 /opt/syco/etc/iso /media/dvd")

        if not os.access("/media/dvd/RPM-GPG-KEY-CentOS-6", os.F_OK):
            raise Exception("Couldn't mount dvd")

    @staticmethod
    def unmount_dvd():
        x("umount /media/dvd")

    def create_kickstart(self):
        '''
        Create the kickstart file that should be used during installation.

        '''
        ks_folder = app.SYCO_PATH + "var/kickstart/generated/"
        hostname_ks_file = ks_folder + self.hostname + ".ks"
        dvd_ks_file = app.SYCO_PATH + "var/kickstart/dvd-guest.ks"

        x("mkdir -p " + ks_folder)
        x("cp " + dvd_ks_file + " " + hostname_ks_file)
        x("chmod 744 %s" % hostname_ks_file)

        set_config_property_batch(hostname_ks_file, self.property_list, False)

    @staticmethod
    def start_nfs_export():
        nfs.add_export("kickstart", app.SYCO_PATH + "var/kickstart/generated/")
        nfs.add_export("dvd", "/media/dvd/")
        nfs.configure_with_static_ip()
        nfs.restart_services()
        nfs.add_iptables_rules()

    @staticmethod
    def stop_nfs_export(self):
        nfs.remove_iptables_rules()
        nfs.stop_services()
        time.sleep(1)
        nfs.remove_export("kickstart")
        nfs.remove_export('dvd')

    def create_kvm_host(self):
        devicename = disk.create_lvm_volumegroup(
            self.hostname,
            int(self.property_list['\$total_disk_gb']) + 1,
            config.host(self.hostname).get_vol_group())

        cmd = " virt-install"
        cmd += " -d --connect qemu:///system"
        cmd += " --name " + self.hostname
        cmd += " --ram " + self.ram
        cmd += " --vcpus=" + self.cpu
        if self.cpu_max is not None and self.cpu_max != "": cmd += ",maxvcpus=" + self.cpu_max
        cmd += " --vnc --noautoconsole"
        cmd += " --hvm"
        cmd += " --virt-type=kvm"
        cmd += " --autostart"
        cmd += " --disk path=" + devicename
        cmd += " --os-variant=rhel6"
        cmd += " --arch x86_64"
        if config.general.is_back_enabled(): cmd += " --network bridge:br0"
        cmd += " --network bridge:br1"
        cmd += " --location nfs:" + self.kvm_host_ip + ":/dvd"
        cmd += ' -x "ks=nfs:' + self.kvm_host_ip + ':/kickstart/' + self.hostname + '.ks'
        cmd += ' ksdevice=eth1'
        cmd += ' ip=' + config.host(self.hostname).get_front_ip()
        cmd += ' netmask=' + config.general.get_front_netmask()
        cmd += ' dns=' + config.general.get_front_resolver_ip()
        cmd += ' gateway=' + self.kvm_host_ip
        cmd += ' "'

        x(cmd)
        self.wait_for_installation_to_complete()
        self.autostart_guests()

    def wait_for_installation_to_complete(self):
        '''
        Waiting for the installation process to complete, and halt the guest.

        '''
        app.print_verbose("Wait for installation of " + self.hostname +
                          " to complete", new_line=False)
        while True:
            time.sleep(10)
            print ".",
            sys.stdout.flush()
            result = x("virsh list", output=False)
            if self.hostname not in result:
                print "Now installed"
                break

    def autostart_guests(self):
        # Autostart guests.
        x("virsh autostart " + self.hostname)
        x("virsh start " + self.hostname)
