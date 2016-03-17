# -*- coding: utf-8 -*-
"""
Created on Mon Feb 29 16:02:18 2016

@author: hendrik
"""
import logging
import pandas as pd
import numpy as np

from oemof import db
from oemof.db import tools
from oemof.db import powerplants as db_pps
from oemof.db import feedin_pg
from oemof.tools import logger
from oemof.core import energy_system as es
from oemof.solph import predefined_objectives as predefined_objectives
from oemof.core.network.entities import Bus
from oemof.core.network.entities.components import sources as source
from oemof.core.network.entities.components import sinks as sink
from oemof.core.network.entities.components import transformers as transformer
from oemof.core.network.entities.components import transports as transport
from oemof.demandlib import demand as dm

de_en = {
    'Braunkohle': 'lignite',
    'lignite': 'lignite',
    'Steinkohle': 'hard_coal',
    'coal': 'hard_coal',
    'Erdgas': 'natural_gas',
    'Öl': 'oil',
    'oil': 'oil',
    'Solarstrom': 'solar_power',
    'Windkraft': 'wind_power',
    'Biomasse': 'biomass',
    'biomass': 'biomass',
    'Wasserkraft': 'hydro_power',
    'run_of_river': 'hydro_power',
    'Gas': 'methan',
    'Mineralölprodukte': 'mineral_oil',
    'Abfall': 'waste',
    'waste': 'waste',
    'Sonstige Energieträger\n(nicht erneuerbar) ': 'waste',
    'other_non_renewable': 'waste',
    'Pumpspeicher': 'pumped_storage',
    'pumped_storage':'pumped_storage',    
    'Erdwärme': 'geo_heat',
    'gas': 'natural_gas'}

translator = lambda x: de_en[x]


def get_parameters():
# emission factors in t/MWh			############Parameter erstmal über Tabelle einlesen??
	co2_emissions = {}
	co2_emissions['lignite'] = 0.111 * 3.6
	co2_emissions['hard_coal'] = 0.0917 * 3.6
	co2_emissions['natural_gas'] = 0.0556 * 3.6
	co2_emissions['oil'] = 0.0750 * 3.6
	co2_emissions['waste'] = 0.1
	co2_emissions['biomass'] = 0.1
	co2_emissions['pumped_storage'] = 0.001

	# emission factors in t/MW
	co2_fix = {}
	co2_fix['lignite'] = 0.1
	co2_fix['hard_coal'] = 0.1
	co2_fix['natural gas'] = 0.1
	co2_fix['oil'] = 0.1
	co2_fix['waste'] = 0.1
	co2_fix['pumped_storage'] = 0.1
		#decentralized pp
	co2_fix['lignite_dec'] = 0.1
	co2_fix['hard_coal_dec'] = 0.1
	co2_fix['biomass_dec'] = 0.1
	co2_fix['oil_dec'] = 0.1
	co2_fix['gas_dec'] = 0.1
	co2_fix['solar_heat_dec'] = 0.1
	co2_fix['heat_pump_dec'] = 0.1
	co2_fix['waste_dec'] = 0.1
	co2_fix['el_heat_dec'] = 0.1
		#renewables
	co2_fix['pv'] = 0.1
	co2_fix['wind'] = 0.1
	co2_fix['waste_dec'] = 0.1
	co2_fix['biomass'] = 0.1
	co2_fix['waste_dec'] = 0.1
	co2_fix['hydro'] = 0.1

	eta_elec = {}
	eta_elec['lignite'] = 0.35
	eta_elec['hard_coal'] = 0.39
	eta_elec['natural_gas'] = 0.45
	eta_elec['oil'] = 0.40
	eta_elec['waste'] = 0.40
	eta_elec['biomass'] = 0.40
	eta_elec['pumped_storage'] = 0.40

	eta_th = {}
	eta_th['lignite'] = 0.35
	eta_th['hard_coal'] = 0.39
	eta_th['natural_gas'] = 0.45
	eta_th['oil'] = 0.40
	eta_th['waste'] = 0.40
	eta_th['biomass'] = 0.40
	eta_th['pumped_storage'] = 0.40
 
	opex_var = {}
	opex_var['lignite'] = 22
	opex_var['hard_coal'] = 25
	opex_var['natural_gas'] = 22
	opex_var['oil'] = 22
	opex_var['solar_power'] = 1
	opex_var['wind_power'] = 1
	opex_var['waste'] = 1
	opex_var['biomass'] = 1
	opex_var['pumped_storage'] = 1

	capex = {}
	capex['lignite'] = 22
	capex['hard_coal'] = 25
	capex['natural_gas'] = 22
	capex['oil'] = 22
	capex['solar_power'] = 1
	capex['wind_power'] = 1
	capex['waste'] = 1
	capex['biomass'] = 1
	capex['pumped_storage'] = 1

	# price for resource
	price = {}
	price['lignite'] = 60
	price['hard_coal'] = 60
	price['natural_gas'] = 60
	price['oil'] = 60
	price['waste'] = 60
	price['biomass'] = 60
	price['pumped_storage'] = 0
	price['hydro_power'] = 0
 
	return(co2_emissions, co2_fix, eta_elec, eta_th, opex_var, capex, price)


co2_emissions, co2_fix, eta_elec, eta_th, opex_var, capex, price = get_parameters()

def get_dec_heat_demand(conn): 
    sql = """
        SELECT sector, region, demand
        FROM oemof.demand as pp
        """
    df = pd.DataFrame(
        conn.execute(sql).fetchall(), columns=['sector', 'fstate', 'demands'])
    return df

def get_opsd_pps(conn, geometry):
    sql = """
        SELECT fuel, status, chp, capacity, capacity_uba, chp_capacity_uba, 
        efficiency_estimate
        FROM oemof_test.kraftwerke_de_opsd as pp
        WHERE st_contains(
        ST_GeomFromText('{wkt}',4326), ST_Transform(pp.geom, 4326))
        """.format(wkt=geometry.wkt)
    df = pd.DataFrame(
        conn.execute(sql).fetchall(), columns=['type', 'status', 'chp', 
        'cap_el', 'cap_el_uba', 'cap_th_uba', 'efficiency'])
    df['type'] = df['type'].apply(translator)
    return df
    
def entity_exists(esystem, uid):
    return len([obj for obj in esystem.entities if obj.uid == uid]) > 0
	
		
def create_opsd_entity_objects(esystem, region, pp, bclass, **kwargs): #bclass = Bus
    'creates simple, CHP or storage transformer for pp from db'
    if entity_exists(esystem, ('bus', region.name, pp[1].type)):
        logging.debug('Bus {0} exists. Nothing done.'.format(
            ('bus', region.name, pp[1].type)))
        location = region.name # weist existierendem Bus die location region zu
    elif entity_exists(esystem, ('bus', 'global', pp[1].type)):
        logging.debug('Bus {0} exists. Nothing done.'.format(
            ('bus', 'global', pp[1].type)))
        location = 'global' # weist existierendem Bus die location global zu
    else:
        logging.debug('Creating Bus {0}.'.format(
            ('bus', region.name, pp[1].type)))
        bclass(uid=('bus', 'global', pp[1].type), type=pp[1].type,
               price=price[pp[1].type], regions=esystem.regions, excess=False)
        location = 'global' # erstellt Bus für Kraftwerkstyp und weist location global zu
        source.Commodity(
            uid=pp[1].type,
            outputs=[obj for obj in esystem.entities if obj.uid == (
                'bus', location, pp[1].type)]) 
        print('bus und source' + location + pp[1].type + 'erstellt')
                # erstellt source für Kraftwerkstyp

    # todo: getBnEtzA ändern: ich brauche chp und wärmeleistung
    if pp[1].chp == 'yes':
        if pp[1].cap_th_uba is None:
            transformer.CHP(
			uid=('transformer', region.name, pp[1].type, 'chp'),
			inputs=[obj for obj in esystem.entities if obj.uid == (
				'bus', location, pp[1].type)], # nimmt von ressourcenbus
			outputs=[[obj for obj in region.entities if obj.uid == (
				'bus', region.name, 'elec')][0], 
					[obj for obj in region.entities if obj.uid == (
					'bus', region.name, 'dh')][0]], # speist auf strombus und fernwärmebus
			in_max=[None],
                out_max=[[float(pp[1].cap_el)], [float(pp[1].cap_el)*0.2]],
			eta=[eta_elec[pp[1].type], eta_th[pp[1].type]],
			opex_var=opex_var[pp[1].type],
			regions=[region])
        else:
             transformer.CHP(
			uid=('transformer', region.name, pp[1].type, 'chp'),
			inputs=[obj for obj in esystem.entities if obj.uid == (
				'bus', location, pp[1].type)], # nimmt von ressourcenbus
			outputs=[[obj for obj in region.entities if obj.uid == (
				'bus', region.name, 'elec')][0], 
					[obj for obj in region.entities if obj.uid == (
					'bus', region.name, 'dh')][0]], # speist auf strombus und fernwärmebus
			in_max=[None],
                out_max=[[float(pp[1].cap_el_uba)], [float(pp[1].cap_th_uba)]],
			eta=[eta_elec[pp[1].type], eta_th[pp[1].type]],
			opex_var=opex_var[pp[1].type],
			regions=[region]) 
       
    elif pp[1].type =='pumped_storage': ##parameter überprüfen!!!
        transformer.storage(
			uid=('Storage', region.name, pp[1].type),
			inputs=[obj for obj in esystem.entities if obj.uid == (
					'bus', location, 'elec')], # nimmt von strombus
			outputs=[obj for obj in region.entities if obj.uid == (
					'bus', region.name, 'elec')],  # speist auf strombus 
			cap_max=[float(pp[1].cap_el)],
			out_max=[float(pp[1].cap_el)], # inst. Leistung!
			eta_in=[eta_elec['pumped_storage_in']], ####anlegen!!
			eta_out=[eta_elec['pumped_storage_out']],   ####anlegen!!!
			opex_var=opex_var[pp[1].type],
			regions=[region])
			
                               ##scale hydropower profile (csv) 
                               ###with capacity from db as fixed source
    elif pp[1].type =='hydro_power':
        source.FixedSource(
			uid=('FixedSrc', region.name, 'hydro'),
                outputs=[obj for obj in region.entities if obj.uid == (
                'bus', region.name, 'elec')],
			val=scale_profile_to_capacity(
						path=kwargs.get('path_hydro'),
						filename=kwargs.get('filename_hydro'),
						capacity=pp[1].cap_el),                     
                out_max=[float(pp[1].cap_el)],
                regions=[region])
	
			
	#weitere Ausnahmen:	 Wasserkraft? 
			
		#	    transformer.Storage(uid=('sto_simple', region.name, 'elec'),
        #                inputs=bel,
        #                outputs=bel,
        #                eta_in=1,
        #                eta_out=0.8,
        #                cap_loss=0.00,
        #                opex_fix=35,
        #                opex_var=0,
        #                capex=1000,
        #                cap_max=10 ** 12,
        #                cap_initial=0,
        #                c_rate_in=1/6,	????
        #                c_rate_out=1/6)	?????
	  ###create transformer.storage
	 
    else:
        transformer.Simple( 
			uid=('transformer', region.name, pp[1].type),
			inputs=[obj for obj in esystem.entities if obj.uid == (
					'bus', location, pp[1].type)], # nimmt von ressourcenbus
			outputs=[obj for obj in region.entities if obj.uid == (
					'bus', region.name, 'elec')], # speist auf strombus
			in_max=[None],
			out_max=[float(pp[1].cap_el)], # inst. Leistung!
			eta=[eta_elec[pp[1].type]], 
			opex_var=opex_var[pp[1].type],
			regions=[region])
			
			
def create_opsd_summed_objects(esystem, region, pp, bclass, chp_faktor, **kwargs): #bclass = Bus
    'creates entities for each type generation'
    typeofgen = kwargs.get('typeofgen')
    
    # replace NaN with 0
    mask = pd.isnull(pp)
    pp = pp.where(~mask, other=0)
    
    capacity = {}  
    capacity_chp_el = {}
    capacity_chp_th = {}
    efficiency = {}
    for typ in typeofgen:
        capacity[typ] = sum(pp[pp['type'].isin([typ])][pp['status'].isin([
        'operating'])][pp['chp'].isin(['no'])]['cap_el'])
        
        capacity_chp_el[typ] = sum(pp[pp['type'].isin([typ])][pp['status'].isin([
        'operating'])][pp['chp'].isin(['yes'])]['cap_el_uba']) + sum(
        pp[pp['type'].isin([typ])][pp['status'].isin([
        'operating'])][pp['chp'].isin(['yes'])][pp['cap_th_uba'].isin(
        ['none'])]['cap_el'])        
        
        capacity_chp_th[typ] = float(sum(pp[pp['type'].isin([typ])][pp['status'].isin([
        'operating'])][pp['chp'].isin(['yes'])]['cap_th_uba'])) + float(sum( 
        pp[pp['type'].isin([typ])][pp['status'].isin([
        'operating'])][pp['chp'].isin(['yes'])][pp['cap_th_uba'].isin(
        ['none'])]['cap_el'])*chp_faktor)
        
        efficiency[typ] = np.mean(pp[pp['type'].isin([typ])][pp['status'].isin([
        'operating'])][pp['chp'].isin(['no'])]['efficiency'])
        
        print(typ, capacity[typ])  
        print(capacity_chp_el[typ])  
        print(capacity_chp_th[typ])  
        print(efficiency[typ])


        transformer.CHP(
			uid=('transformer', region.name, typ, 'chp'),
			inputs=[obj for obj in esystem.entities if obj.uid == (
				'bus', 'global', typ)], # nimmt von ressourcenbus
			outputs=[[obj for obj in region.entities if obj.uid == (
				'bus', region.name, 'elec')][0], 
					[obj for obj in region.entities if obj.uid == (
					'bus', region.name, 'dh')][0]], # speist auf strombus und fernwärmebus
			in_max=[None],
                out_max=[[float(capacity_chp_el[typ])], [float(capacity_chp_th[typ])]],
			eta=[eta_elec[typ], eta_th[typ]],
			opex_var=opex_var[typ],
			regions=[region])
   
        transformer.Simple(
			uid=('transformer', region.name, typ),
			inputs=[obj for obj in esystem.entities if obj.uid == (
				'bus', 'global', typ)], # nimmt von ressourcenbus
			outputs=[[obj for obj in region.entities if obj.uid == (
				'bus', region.name, 'elec')][0]],
			in_max=[None],
                out_max=[float(capacity[typ])],
			eta=efficiency[typ], 
			opex_var=opex_var[typ],
			regions=[region])
   
       
 #   elif pp[1].type =='pumped_storage': ##parameter überprüfen!!!
 #       transformer.storage(
	#		uid=('Storage', region.name, pp[1].type),
#			inputs=[obj for obj in esystem.entities if obj.uid == (
#					'bus', location, 'elec')], # nimmt von strombus
#			outputs=[obj for obj in region.entities if obj.uid == (
#					'bus', region.name, 'elec')],  # speist auf strombus 
#			cap_max=[float(pp[1].cap_el)],
#			out_max=[float(pp[1].cap_el)], # inst. Leistung!
#			eta_in=[eta_elec['pumped_storage_in']], ####anlegen!!
#			eta_out=[eta_elec['pumped_storage_out']],   ####anlegen!!!
#			opex_var=opex_var[pp[1].type],
#			regions=[region])
#			
 #                              ##scale hydropower profile (csv) 
  #                             ###with capacity from db as fixed source
  #  elif pp[1].type =='hydro_power':
#        source.FixedSource(
#			uid=('FixedSrc', region.name, 'hydro'),
 #               outputs=[obj for obj in region.entities if obj.uid == (
  #              'bus', region.name, 'elec')],
	#		val=scale_profile_to_capacity(
	#					path=kwargs.get('path_hydro'),
#						filename=kwargs.get('filename_hydro'),
#						capacity=pp[1].cap_el),                     
 #               out_max=[float(pp[1].cap_el)],
  #              regions=[region])
	#
			
	#weitere Ausnahmen:	 Wasserkraft? 
			
		#	    transformer.Storage(uid=('sto_simple', region.name, 'elec'),
        #                inputs=bel,
        #                outputs=bel,
        #                eta_in=1,
        #                eta_out=0.8,
        #                cap_loss=0.00,
        #                opex_fix=35,
        #                opex_var=0,
        #                capex=1000,
        #                cap_max=10 ** 12,
        #                cap_initial=0,
        #                c_rate_in=1/6,	????
        #                c_rate_out=1/6)	?????
	  ###create transformer.storage

   
def scale_profile_to_capacity(path, filename, capacity):
	profile = pd.read_csv(filename,
                                   sep=",")
	generation_profile = (profile /
                            profile.max() *
                            capacity)
	return generation_profile